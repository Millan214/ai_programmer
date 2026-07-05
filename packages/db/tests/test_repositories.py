import pytest
from platform_db.repositories import sessions, tasks, turns, verifier_runs
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_create_task_session_turn_and_query_back(db_session: AsyncSession):
    task = await tasks.create(
        db_session,
        repo="org/demo",
        title="add hasPermission helper",
        description="add a hasPermission(user, action) helper with tests",
    )
    assert task.status == "pending"

    fetched_task = await tasks.get(db_session, task.id)
    assert fetched_task is not None
    assert fetched_task.title == task.title

    await tasks.update_status(db_session, task.id, "running")
    fetched_task = await tasks.get(db_session, task.id)
    assert fetched_task is not None
    assert fetched_task.status == "running"

    task_session = await sessions.create(db_session, task_id=task.id, phase="build")
    fetched_session = await sessions.get(db_session, task_session.id)
    assert fetched_session is not None
    assert fetched_session.task_id == task.id

    turn = await turns.create(
        db_session,
        session_id=task_session.id,
        agent="developer",
        model="claude-sonnet-5",
        prompt_version="developer/react@v1",
        input_tokens=120,
        output_tokens=340,
    )
    fetched_turn = await turns.get(db_session, turn.id)
    assert fetched_turn is not None
    assert fetched_turn.session_id == task_session.id

    run = await verifier_runs.create(
        db_session,
        session_id=task_session.id,
        worktree_ref="refs/worktrees/abc123",
        tests={"passed": 12, "failed": 0},
    )
    fetched_run = await verifier_runs.get(db_session, run.id)
    assert fetched_run is not None
    assert fetched_run.tests == {"passed": 12, "failed": 0}
