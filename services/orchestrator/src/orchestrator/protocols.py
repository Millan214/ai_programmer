"""Agent interfaces the orchestrator depends on, plus their Phase 0 fakes.

The real implementations land in later cards: PlannerAgent (04), DeveloperAgent (08),
Verifier (05). Until then the graph runs against the fakes defined here.

Phase 0 protocols exchange JSON-serializable dicts, not the concrete Pydantic models
(``Plan`` etc.) that later cards introduce. This keeps the dependency arrow one-way
(planner/developer packages depend on the orchestrator's protocols, never the reverse)
and matches what the graph carries in ``TaskState`` and what Postgres stores as JSONB.
The real ``PlannerAgent`` wraps its typed ``Plan`` back to a dict at the protocol
boundary (see ``planner.adapter``).

``PlannerProtocol.plan`` and ``DeveloperProtocol.build`` also carry ``session_id`` so a
real agent can write its own ``agent_turn`` rows (with the true model/tokens/cost) via
the ``TurnRecorder`` it was constructed with; ``build`` additionally carries ``repo``
because the Developer's retrieval and sandbox spawn are per-repo.
``VerifierProtocol.verify`` carries ``session_id`` too, so the real Verifier service can
persist each run as a ``verifier_run`` row linked to the session. Fakes ignore all of it.
"""

import uuid
from decimal import Decimal
from typing import Protocol

PlanDict = dict[str, object]
EditsDict = dict[str, object]
VerifierFacts = dict[str, object]


class TurnRecorder(Protocol):
    """Callable that persists an ``agent_turn`` row on behalf of a real agent.

    Bound at wiring time to ``PersistenceProtocol.record_agent_turn``. Kept as its own
    small protocol so agents don't take a dependency on the full persistence surface.
    """

    async def __call__(
        self,
        *,
        session_id: uuid.UUID,
        agent: str,
        model: str,
        prompt_version: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: Decimal | None,
        tool_calls: dict[str, object] | None = None,
        output_ref: str | None = None,
    ) -> None: ...


class PlannerProtocol(Protocol):
    async def plan(self, task_description: str, session_id: uuid.UUID) -> PlanDict: ...


class DeveloperProtocol(Protocol):
    async def build(self, plan: PlanDict, repo: str, session_id: uuid.UUID) -> EditsDict: ...


class SandboxCleanup(Protocol):
    """End-of-run teardown for the sandbox a real Developer left alive for Verify."""

    async def __call__(self, sandbox_id: str) -> None: ...


class VerifierProtocol(Protocol):
    async def verify(self, edits: EditsDict, session_id: uuid.UUID) -> VerifierFacts: ...


class FakePlanner:
    """Returns a fixed stub plan. Replaced by card 04's PlannerAgent.

    Accepts an optional ``TurnRecorder`` so fake-planner runs still write an
    ``agent_turn`` row (a placeholder one), matching the shape of what the real
    Planner will write. Card 03's DB integration test relies on this to see four turns
    per run.
    """

    def __init__(self, recorder: TurnRecorder | None = None) -> None:
        self._recorder = recorder

    async def plan(self, task_description: str, session_id: uuid.UUID) -> PlanDict:
        if self._recorder is not None:
            await self._recorder(
                session_id=session_id,
                agent="planner",
                model="fake",
                prompt_version="planner@fake",
                input_tokens=0,
                output_tokens=0,
                cost_usd=Decimal(0),
                tool_calls={},
            )
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
    """Returns fixed stub edits. Replaced by card 08's DeveloperAgent.

    Like ``FakePlanner``, accepts an optional ``TurnRecorder`` so fake-developer runs
    still write a placeholder ``agent_turn`` row, matching the real agent's shape
    (one row per ReAct iteration; the fake "iterates" once).
    """

    def __init__(self, recorder: TurnRecorder | None = None) -> None:
        self._recorder = recorder

    async def build(self, plan: PlanDict, repo: str, session_id: uuid.UUID) -> EditsDict:
        if self._recorder is not None:
            await self._recorder(
                session_id=session_id,
                agent="developer",
                model="fake",
                prompt_version="developer@fake",
                input_tokens=0,
                output_tokens=0,
                cost_usd=Decimal(0),
                tool_calls={},
            )
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

    async def verify(self, edits: EditsDict, session_id: uuid.UUID) -> VerifierFacts:
        return dict(self._facts)
