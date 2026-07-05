"""HTTP surface tests.

``test_verify_endpoint_returns_valid_result`` monkeypatches ``verify`` so it exercises
real request/response wiring without needing the fixtures' node_modules installed —
``test_runners.py``'s integration tests cover the real toolchain end to end.
"""

# httpx's ``Client.post`` return type threads through several partially-generic
# overloads that pyright strict can't fully resolve, so `response` and everything
# derived from it (`.status_code`, `.json()`) comes back as Unknown; the assertions
# below are the actual type check.
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from verifier.models import BuildResult, LintResult, TypecheckResult, VerifierResult
from verifier.models import TestResult as VerifierTestResult
from verifier.service import app

FIXTURES = Path(__file__).parent / "fixtures"
PASSING_PROJECT = FIXTURES / "passing-project"

client = TestClient(app)

_STUB_RESULT = VerifierResult(
    build=BuildResult(status="pass"),
    typecheck=TypecheckResult(status="pass"),
    tests=VerifierTestResult(status="pass", total=1, passed=1),
    lint=LintResult(status="pass"),
)


def test_verify_endpoint_returns_valid_result(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_verify(cwd: Path) -> VerifierResult:
        return _STUB_RESULT

    monkeypatch.setattr("verifier.service.verify", fake_verify)

    response = client.post("/verify", json={"worktree_path": str(PASSING_PROJECT)})

    assert response.status_code == 200
    result = VerifierResult.model_validate(response.json())
    assert result.build.status == "pass"
    assert result.tests.total == 1


def test_verify_endpoint_rejects_nonexistent_path() -> None:
    response = client.post("/verify", json={"worktree_path": "/does/not/exist"})
    assert response.status_code == 400


@pytest.mark.integration
def test_verify_endpoint_real_toolchain_on_passing_project() -> None:
    if shutil.which("pnpm") is None:
        pytest.skip("pnpm not on PATH")
    if not (PASSING_PROJECT / "node_modules").is_dir():
        pytest.skip("passing-project fixture has no node_modules — run `pnpm install` in it")

    response = client.post("/verify", json={"worktree_path": str(PASSING_PROJECT)})

    assert response.status_code == 200
    result = VerifierResult.model_validate(response.json())
    assert result.build.status == "pass"
    assert result.typecheck.status == "pass"
    assert result.tests.status == "pass"
    assert result.lint.status == "pass"
