import uuid

import pytest
from orchestrator.graph import Orchestrator
from orchestrator.persistence import TaskInfo
from orchestrator.protocols import FakeDeveloper, FakePlanner, FakeVerifier
from sqlalchemy import select


class FakePersistence:
    """In-memory PersistenceProtocol impl; records calls so unit tests avoid the DB."""

    def __init__(self) -> None:
        self.opened: list[uuid.UUID] = []
        self.nodes: list[tuple[str, str, str | None]] = []
        self.statuses: list[str] = []
        self._session_id = uuid.uuid4()

    async def load_task(self, task_id: uuid.UUID) -> TaskInfo:
        return TaskInfo(description="stub", repo="demo-lib", budget_remaining=0.0)

    async def open_session(self, task_id: uuid.UUID) -> uuid.UUID:
        self.opened.append(task_id)
        return self._session_id

    async def record_node(
        self, session_id: uuid.UUID, phase: str, agent: str, output_ref: str | None = None
    ) -> None:
        self.nodes.append((phase, agent, output_ref))

    async def set_task_status(self, task_id: uuid.UUID, status: str) -> None:
        self.statuses.append(status)


@pytest.mark.asyncio
async def test_full_run_transitions_all_phases_and_completes() -> None:
    persistence = FakePersistence()
    orch = Orchestrator(FakePlanner(), FakeDeveloper(), FakeVerifier(), persistence)
    task_id = uuid.uuid4()

    await orch.execute(task_id)

    assert persistence.opened == [task_id]
    assert [phase for phase, _, _ in persistence.nodes] == ["plan", "build", "verify", "ship"]
    assert [agent for _, agent, _ in persistence.nodes] == [
        "planner",
        "developer",
        "verifier",
        "shipper",
    ]
    assert persistence.statuses == ["completed"]

    # The ship turn carries the fake PR URL as its output_ref.
    _, _, ship_output_ref = persistence.nodes[-1]
    assert ship_output_ref is not None
    assert ship_output_ref.endswith(str(task_id))


@pytest.mark.asyncio
async def test_failed_verify_does_not_ship() -> None:
    persistence = FakePersistence()
    failing_verifier = FakeVerifier({"build": "fail", "tests": "pass"})
    orch = Orchestrator(FakePlanner(), FakeDeveloper(), failing_verifier, persistence)
    task_id = uuid.uuid4()

    await orch.execute(task_id)

    assert [phase for phase, _, _ in persistence.nodes] == ["plan", "build", "verify"]
    assert persistence.statuses == ["failed_verify"]


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
