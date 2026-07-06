"""Result shapes for the Developer agent (card 08).

``BuildResult`` here is the *agent's* outcome (did the loop converge), distinct from
``verifier.models.BuildResult`` (did ``pnpm build`` pass) — same name, different axis.
``verifier_facts`` is always a full ``VerifierResult``; when the loop exits before any
verifier call ran, it carries all-``skip`` statuses rather than pretending to know.
"""

from typing import Literal

from pydantic import BaseModel
from verifier.models import (
    BuildResult as VerifierBuildResult,
)
from verifier.models import (
    LintResult,
    TestResult,
    TypecheckResult,
    VerifierResult,
)

BuildStatus = Literal["passed", "budget_exceeded", "stuck", "max_iterations"]


class BuildResult(BaseModel):
    status: BuildStatus
    diff: str
    verifier_facts: VerifierResult


class DeveloperError(Exception):
    """Raised when the loop cannot run at all (a backing service is unreachable)."""


def skipped_verifier_result() -> VerifierResult:
    """The honest default when the loop exits before the Verifier ever ran."""
    return VerifierResult(
        build=VerifierBuildResult(status="skip"),
        typecheck=TypecheckResult(status="skip"),
        tests=TestResult(status="skip"),
        lint=LintResult(status="skip"),
    )
