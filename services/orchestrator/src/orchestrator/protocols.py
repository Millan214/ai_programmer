"""Agent interfaces the orchestrator depends on, plus their Phase 0 fakes.

The real implementations land in later cards: PlannerAgent (04), DeveloperAgent (08),
Verifier (05). Until then the graph runs against the fakes defined here.

Phase 0 protocols exchange JSON-serializable dicts, not the concrete Pydantic models
(``Plan`` etc.) that later cards introduce. This keeps the dependency arrow one-way
(planner/developer packages depend on the orchestrator's protocols, never the reverse)
and matches what the graph carries in ``TaskState`` and what Postgres stores as JSONB.
When card 04 gives the Planner a real ``Plan`` model, its ``plan()`` should return
``plan.model_dump()`` to keep satisfying ``PlannerProtocol``.
"""

from typing import Protocol

PlanDict = dict[str, object]
EditsDict = dict[str, object]
VerifierFacts = dict[str, object]


class PlannerProtocol(Protocol):
    async def plan(self, task_description: str) -> PlanDict: ...


class DeveloperProtocol(Protocol):
    async def build(self, plan: PlanDict) -> EditsDict: ...


class VerifierProtocol(Protocol):
    async def verify(self, edits: EditsDict) -> VerifierFacts: ...


class FakePlanner:
    """Returns a fixed stub plan. Replaced by card 04's PlannerAgent."""

    async def plan(self, task_description: str) -> PlanDict:
        return {
            "subtasks": [
                {
                    "title": "stub subtask",
                    "description": f"stub plan for: {task_description}",
                    "acceptance": "stub",
                }
            ],
            "risks": [],
            "estimated_files": [],
        }


class FakeDeveloper:
    """Returns fixed stub edits. Replaced by card 08's DeveloperAgent."""

    async def build(self, plan: PlanDict) -> EditsDict:
        return {"diff": "--- stub diff ---", "files": []}


class FakeVerifier:
    """Returns fixed facts (pass by default). Replaced by card 05's Verifier.

    Accepts an override so tests can simulate a failing verify.
    """

    def __init__(self, facts: VerifierFacts | None = None) -> None:
        self._facts: VerifierFacts = facts if facts is not None else {
            "build": "pass",
            "tests": "pass",
        }

    async def verify(self, edits: EditsDict) -> VerifierFacts:
        return dict(self._facts)
