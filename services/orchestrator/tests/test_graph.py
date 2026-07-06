import uuid
from decimal import Decimal

import pytest
from orchestrator.graph import Orchestrator
from orchestrator.persistence import TaskInfo
from orchestrator.protocols import FakeDeveloper, FakePlanner, FakeVerifier
from sqlalchemy import select


class FakePersistence:
    """In-memory PersistenceProtocol impl; records calls so unit tests avoid the DB.

    ``nodes`` captures the phases that go through ``record_node`` (build/verify/ship in
    Phase 0 — the fake-agent path that also stamps a placeholder turn). ``phase_advances``
    captures the phase-only ``advance_phase`` calls (the plan node uses this path so the
    Planner can write its own real turn). ``agent_turns`` captures the real-turn writes
    routed through ``record_agent_turn`` — with fakes wired we expect one row for the
    plan phase (FakePlanner uses its recorder to stamp a placeholder).
    """

    def __init__(self) -> None:
        self.opened: list[uuid.UUID] = []
        self.nodes: list[tuple[str, str, str | None]] = []
        self.phase_advances: list[tuple[uuid.UUID, str]] = []
        self.agent_turns: list[dict[str, object]] = []
        self.statuses: list[str] = []
        self._session_id = uuid.uuid4()

    async def load_task(self, task_id: uuid.UUID) -> TaskInfo:
        return TaskInfo(description="stub", repo="demo-lib", budget_remaining=0.0)

    async def open_session(self, task_id: uuid.UUID) -> uuid.UUID:
        self.opened.append(task_id)
        return self._session_id

    async def advance_phase(self, session_id: uuid.UUID, phase: str) -> None:
        self.phase_advances.append((session_id, phase))

    async def record_node(
        self, session_id: uuid.UUID, phase: str, agent: str, output_ref: str | None = None
    ) -> None:
        self.phase_advances.append((session_id, phase))
        self.nodes.append((phase, agent, output_ref))

    async def record_agent_turn(
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
    ) -> None:
        self.agent_turns.append(
            {
                "session_id": session_id,
                "agent": agent,
                "model": model,
                "prompt_version": prompt_version,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": cost_usd,
                "tool_calls": tool_calls,
                "output_ref": output_ref,
            }
        )

    async def set_task_status(self, task_id: uuid.UUID, status: str) -> None:
        self.statuses.append(status)


@pytest.mark.asyncio
async def test_full_run_transitions_all_phases_and_completes() -> None:
    persistence = FakePersistence()
    planner = FakePlanner(recorder=persistence.record_agent_turn)
    developer = FakeDeveloper(recorder=persistence.record_agent_turn)
    orch = Orchestrator(planner, developer, FakeVerifier(), persistence)
    task_id = uuid.uuid4()

    await orch.execute(task_id)

    assert persistence.opened == [task_id]
    # Every phase advances the task_session — plan/build via ``advance_phase`` (their
    # agents write their own turns), verify/ship via ``record_node``
    # (which advances-and-writes-placeholder).
    assert [phase for _, phase in persistence.phase_advances] == [
        "plan",
        "build",
        "verify",
        "ship",
    ]
    # ``record_node`` fires only for the fake verify/ship path — plan and build go
    # through their agents' own turn writes, not through ``record_node``.
    assert [phase for phase, _, _ in persistence.nodes] == ["verify", "ship"]
    assert [agent for _, agent, _ in persistence.nodes] == ["verifier", "shipper"]
    # FakePlanner and FakeDeveloper used their recorders to stamp placeholder rows.
    assert [turn["agent"] for turn in persistence.agent_turns] == ["planner", "developer"]
    assert all(turn["model"] == "fake" for turn in persistence.agent_turns)

    assert persistence.statuses == ["completed"]

    # The ship turn carries the fake PR URL as its output_ref.
    _, _, ship_output_ref = persistence.nodes[-1]
    assert ship_output_ref is not None
    assert ship_output_ref.endswith(str(task_id))


@pytest.mark.asyncio
async def test_failed_verify_does_not_ship() -> None:
    persistence = FakePersistence()
    planner = FakePlanner(recorder=persistence.record_agent_turn)
    failing_verifier = FakeVerifier({"build": "fail", "tests": "pass"})
    orch = Orchestrator(planner, FakeDeveloper(), failing_verifier, persistence)
    task_id = uuid.uuid4()

    await orch.execute(task_id)

    assert [phase for _, phase in persistence.phase_advances] == ["plan", "build", "verify"]
    assert [phase for phase, _, _ in persistence.nodes] == ["verify"]
    assert persistence.statuses == ["failed_verify"]


@pytest.mark.asyncio
async def test_sandbox_cleanup_runs_after_the_run() -> None:
    """A developer that leaves a sandbox alive for Verify gets it torn down at end of run."""
    persistence = FakePersistence()
    cleaned: list[str] = []

    class _SandboxDeveloper:
        async def build(
            self, plan: dict[str, object], repo: str, session_id: uuid.UUID
        ) -> dict[str, object]:
            return {"diff": "real diff", "worktree_path": "/tmp/sb-1", "sandbox_id": "sb-1"}

    async def cleanup(sandbox_id: str) -> None:
        cleaned.append(sandbox_id)

    orch = Orchestrator(
        FakePlanner(), _SandboxDeveloper(), FakeVerifier(), persistence, sandbox_cleanup=cleanup
    )

    await orch.execute(uuid.uuid4())

    assert cleaned == ["sb-1"]
    assert persistence.statuses == ["completed"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_run_persists_task_session_and_turns_to_postgres() -> None:
    from orchestrator.main import run
    from platform_db.models import AgentTurn, TaskSession
    from platform_db.repositories import tasks
    from platform_db.session import session_factory

    async with session_factory()() as db:
        task = await tasks.create(db, repo="demo-lib", title="test", description="stub")
        await db.commit()
        task_id = task.id

    await run(task_id)

    async with session_factory()() as db:
        refreshed = await tasks.get(db, task_id)
        assert refreshed is not None
        assert refreshed.status == "completed"

        sessions_result = await db.execute(
            select(TaskSession).where(TaskSession.task_id == task_id)
        )
        task_sessions = sessions_result.scalars().all()
        assert len(task_sessions) == 1

        turns_result = await db.execute(
            select(AgentTurn).where(AgentTurn.session_id == task_sessions[0].id)
        )
        assert len(turns_result.scalars().all()) == 4
