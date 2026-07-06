"""Runners that shell out to the pnpm/TypeScript toolchain and parse structured facts.

Two deviations from the tool invocations one might guess at, found by running the real
tools against ``tests/fixtures/*`` before writing any parsing code:

- Getting vitest's json reporter through ``pnpm test`` is unreliable: bare
  ``pnpm test --reporter=json`` silently drops the flag (pnpm treats it as its own
  unrecognized option), and the documented fix — a ``--`` separator — was itself
  observed to forward inconsistently across pnpm invocation contexts (worked from an
  interactive shell, forwarded ``--`` itself as a literal arg when spawned via
  ``create_subprocess_shell``). ``pnpm exec vitest run --reporter=json`` sidesteps the
  ambiguity entirely, the same way the lint/typecheck runners call their tools directly.
- ``tsc`` (both ``--noEmit`` and a real build) writes its ``file(line,col): error
  TSxxxx: ...`` diagnostics to stdout, not stderr.

``parse_tsc_errors``/``parse_vitest_json``/``parse_biome_json`` are exported (no leading
underscore) purely so ``tests/test_runners.py`` can pin them against captured real-tool
output without a subprocess; ``build``/``typecheck``/``test``/``lint`` are the module's
actual public surface.
"""

import asyncio
import json
import re
import sys
from pathlib import Path
from typing import cast

from platform_telemetry import traced
from pydantic import BaseModel, Field

from verifier.models import (
    BuildResult,
    LintIssue,
    LintResult,
    Status,
    TestFailure,
    TestResult,
    TypecheckError,
    TypecheckResult,
)

_TSC_ERROR_RE = re.compile(
    r"^(?P<file>.+?)\((?P<line>\d+),(?P<column>\d+)\): error (?P<code>TS\d+): (?P<message>.+)$"
)

# Trailing tail kept when a failing build's combined output is reported back verbatim.
_ERROR_TAIL_CHARS = 4000


async def _run(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
    # pnpm on Windows resolves to a `.cmd` shim, which `create_subprocess_exec` cannot
    # launch directly (CreateProcess needs an actual PE executable); routing through a
    # shell resolves the shim the same way a real terminal invocation would.
    if sys.platform == "win32":
        proc = await asyncio.create_subprocess_shell(
            " ".join(cmd),
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    else:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    stdout, stderr = await proc.communicate()
    return (
        proc.returncode or 0,
        stdout.decode(errors="replace"),
        stderr.decode(errors="replace"),
    )


def _extract_json_object(output: str) -> dict[str, object] | None:
    """Pull the JSON object out of output that may be wrapped in pnpm's run banner."""
    start = output.find("{")
    end = output.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        parsed = json.loads(output[start : end + 1])
    except json.JSONDecodeError:
        return None
    return cast("dict[str, object]", parsed) if isinstance(parsed, dict) else None


@traced("verifier.build")
async def build(cwd: Path) -> BuildResult:
    code, stdout, stderr = await _run(["pnpm", "build"], cwd)
    if code == 0:
        return BuildResult(status="pass")
    combined = (stdout + stderr).strip()
    return BuildResult(status="fail", error=combined[-_ERROR_TAIL_CHARS:])


def parse_tsc_errors(output: str) -> list[TypecheckError]:
    errors: list[TypecheckError] = []
    for line in output.splitlines():
        match = _TSC_ERROR_RE.match(line.strip())
        if match is None:
            continue
        errors.append(
            TypecheckError(
                file=match.group("file"),
                line=int(match.group("line")),
                column=int(match.group("column")),
                code=match.group("code"),
                message=match.group("message"),
            )
        )
    return errors


@traced("verifier.typecheck")
async def typecheck(cwd: Path) -> TypecheckResult:
    code, stdout, stderr = await _run(["pnpm", "exec", "tsc", "--noEmit"], cwd)
    errors = parse_tsc_errors(stdout + stderr)
    status: Status = "pass" if code == 0 and not errors else "fail"
    return TypecheckResult(status=status, errors=errors)


class _VitestAssertion(BaseModel):
    fullName: str | None = None
    title: str | None = None
    status: str
    failureMessages: list[str] = []


class _VitestSuite(BaseModel):
    assertionResults: list[_VitestAssertion] = []


class _VitestReport(BaseModel):
    numTotalTests: int = 0
    numPassedTests: int = 0
    numFailedTests: int = 0
    testResults: list[_VitestSuite] = []


def parse_vitest_json(output: str, *, ran_clean: bool) -> TestResult:
    payload = _extract_json_object(output)
    if payload is None:
        return TestResult(status="pass" if ran_clean else "fail")

    report = _VitestReport.model_validate(payload)
    failures = [
        TestFailure(
            name=assertion.fullName or assertion.title or "unknown",
            message="\n".join(assertion.failureMessages),
        )
        for suite in report.testResults
        for assertion in suite.assertionResults
        if assertion.status == "failed"
    ]
    status: Status = (
        "skip" if report.numTotalTests == 0 else ("pass" if report.numFailedTests == 0 else "fail")
    )
    return TestResult(
        status=status,
        total=report.numTotalTests,
        passed=report.numPassedTests,
        failed=report.numFailedTests,
        failures=failures,
    )


@traced("verifier.test")
async def test(cwd: Path) -> TestResult:
    code, stdout, _stderr = await _run(["pnpm", "exec", "vitest", "run", "--reporter=json"], cwd)
    return parse_vitest_json(stdout, ran_clean=code == 0)


class _BiomePath(BaseModel):
    file: str = "unknown"


class _BiomeLocation(BaseModel):
    path: _BiomePath = Field(default_factory=_BiomePath)


class _BiomeDiagnostic(BaseModel):
    severity: str
    description: str = ""
    location: _BiomeLocation = Field(default_factory=_BiomeLocation)


class _BiomeSummary(BaseModel):
    errors: int = 0
    warnings: int = 0


class _BiomeReport(BaseModel):
    summary: _BiomeSummary = Field(default_factory=_BiomeSummary)
    diagnostics: list[_BiomeDiagnostic] = []


def parse_biome_json(output: str, *, ran_clean: bool) -> LintResult:
    payload = _extract_json_object(output)
    if payload is None:
        return LintResult(status="pass" if ran_clean else "fail")

    report = _BiomeReport.model_validate(payload)
    issues = [
        LintIssue(
            file=diagnostic.location.path.file,
            severity=diagnostic.severity,
            message=diagnostic.description,
        )
        for diagnostic in report.diagnostics
        if diagnostic.severity in ("error", "warning")
    ]
    status: Status = "pass" if report.summary.errors == 0 else "fail"
    return LintResult(
        status=status, errors=report.summary.errors, warnings=report.summary.warnings, issues=issues
    )


@traced("verifier.lint")
async def lint(cwd: Path) -> LintResult:
    code, stdout, _stderr = await _run(["pnpm", "exec", "biome", "check", "--reporter=json"], cwd)
    return parse_biome_json(stdout, ran_clean=code == 0)
