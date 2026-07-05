"""Pydantic result models matching ADR-0006's structured Verifier output."""

from typing import Literal

from pydantic import BaseModel

Status = Literal["pass", "fail", "skip"]


class BuildResult(BaseModel):
    status: Status
    error: str | None = None


class TypecheckError(BaseModel):
    file: str
    line: int
    column: int
    code: str
    message: str


class TypecheckResult(BaseModel):
    status: Status
    errors: list[TypecheckError] = []


class TestFailure(BaseModel):
    name: str
    message: str


class TestResult(BaseModel):
    status: Status
    total: int = 0
    passed: int = 0
    failed: int = 0
    failures: list[TestFailure] = []


class LintIssue(BaseModel):
    file: str
    severity: Literal["error", "warning"]
    message: str


class LintResult(BaseModel):
    status: Status
    errors: int = 0
    warnings: int = 0
    issues: list[LintIssue] = []


class VerifierResult(BaseModel):
    build: BuildResult
    typecheck: TypecheckResult
    tests: TestResult
    lint: LintResult
