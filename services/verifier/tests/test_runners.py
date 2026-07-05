"""Runner tests split in two layers:

- Parser unit tests feed the real (captured) output shapes of tsc/vitest/biome
  straight into the ``parse_*`` functions — fast, deterministic, no subprocess.
- Integration tests shell out to the real pnpm/tsc/vitest/biome toolchain against
  ``tests/fixtures/*`` (each fixture is installed standalone: see its own
  ``pnpm-workspace.yaml`` with ``allowBuilds``, which walls it off from this repo's
  root pnpm workspace and approves biome/esbuild's postinstall scripts). Skipped if
  pnpm or the fixtures' ``node_modules`` aren't present.
"""

import shutil
from pathlib import Path

import pytest
from verifier.runners.pnpm import parse_biome_json, parse_tsc_errors, parse_vitest_json

FIXTURES = Path(__file__).parent / "fixtures"
PASSING_PROJECT = FIXTURES / "passing-project"
FAILING_PROJECT = FIXTURES / "failing-project"


def _require_fixture_toolchain(project: Path) -> None:
    if shutil.which("pnpm") is None:
        pytest.skip("pnpm not on PATH")
    if not (project / "node_modules").is_dir():
        pytest.skip(f"{project} has no node_modules — run `pnpm install` in it first")


# --- parser unit tests -------------------------------------------------------------


def testparse_tsc_errors_matches_real_output() -> None:
    output = "src/math.ts(6,9): error TS2322: Type 'string' is not assignable to type 'number'.\n"
    errors = parse_tsc_errors(output)
    assert len(errors) == 1
    assert errors[0].file == "src/math.ts"
    assert errors[0].line == 6
    assert errors[0].column == 9
    assert errors[0].code == "TS2322"
    assert errors[0].message == "Type 'string' is not assignable to type 'number'."


def testparse_tsc_errors_empty_on_clean_output() -> None:
    assert parse_tsc_errors("") == []


def testparse_vitest_json_passing() -> None:
    output = (
        '{"numTotalTests":1,"numPassedTests":1,"numFailedTests":0,'
        '"testResults":[{"assertionResults":[{"fullName":"add adds two numbers",'
        '"status":"passed","failureMessages":[]}]}]}'
    )
    result = parse_vitest_json(output, ran_clean=True)
    assert result.status == "pass"
    assert result.total == 1
    assert result.passed == 1
    assert result.failed == 0
    assert result.failures == []


def testparse_vitest_json_failing() -> None:
    output = (
        '{"numTotalTests":1,"numPassedTests":0,"numFailedTests":1,'
        '"testResults":[{"assertionResults":[{"fullName":"add adds two numbers",'
        '"status":"failed","failureMessages":["AssertionError: expected 5 to be 999"]}]}]}'
    )
    result = parse_vitest_json(output, ran_clean=False)
    assert result.status == "fail"
    assert result.failed == 1
    assert len(result.failures) == 1
    assert result.failures[0].name == "add adds two numbers"
    assert "expected 5 to be 999" in result.failures[0].message


def testparse_vitest_json_missing_payload_falls_back_to_exit_code() -> None:
    assert parse_vitest_json("not json", ran_clean=True).status == "pass"
    assert parse_vitest_json("not json", ran_clean=False).status == "fail"


def testparse_biome_json_clean() -> None:
    output = '{"summary":{"errors":0,"warnings":0},"diagnostics":[]}'
    result = parse_biome_json(output, ran_clean=True)
    assert result.status == "pass"
    assert result.errors == 0
    assert result.issues == []


def testparse_biome_json_with_lint_error() -> None:
    output = (
        '{"summary":{"errors":1,"warnings":0},'
        '"diagnostics":[{"category":"lint/style/noVar","severity":"error",'
        '"description":"Use let or const instead of var.",'
        '"location":{"path":{"file":"src/math.ts"}}}]}'
    )
    result = parse_biome_json(output, ran_clean=False)
    assert result.status == "fail"
    assert result.errors == 1
    assert len(result.issues) == 1
    assert result.issues[0].file == "src/math.ts"
    assert result.issues[0].severity == "error"
    assert result.issues[0].message == "Use let or const instead of var."


# --- integration tests: real toolchain against the fixtures -------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_passing_project_all_runners_pass() -> None:
    _require_fixture_toolchain(PASSING_PROJECT)
    from verifier.runners import pnpm

    assert (await pnpm.build(PASSING_PROJECT)).status == "pass"
    assert (await pnpm.typecheck(PASSING_PROJECT)).status == "pass"
    assert (await pnpm.test(PASSING_PROJECT)).status == "pass"
    assert (await pnpm.lint(PASSING_PROJECT)).status == "pass"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_failing_project_typecheck_and_tests_fail() -> None:
    _require_fixture_toolchain(FAILING_PROJECT)
    from verifier.runners import pnpm

    typecheck_result = await pnpm.typecheck(FAILING_PROJECT)
    assert typecheck_result.status == "fail"
    assert any(error.code == "TS2322" for error in typecheck_result.errors)

    test_result = await pnpm.test(FAILING_PROJECT)
    assert test_result.status == "fail"
    assert test_result.failed == 1
    assert test_result.failures
