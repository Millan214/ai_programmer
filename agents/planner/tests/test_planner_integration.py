"""Integration test: real Anthropic call + real ``agent_turn`` write.

Skipped unless both an ANTHROPIC_API_KEY is present *and* Postgres is reachable
(``make up`` running). Assertions stay loose on content — LLM output varies — but
strict on the persisted-turn shape and the fact that ``Plan`` parsed at all.
"""

import os
import uuid

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
def skip_without_key() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set — real Anthropic call skipped")


async def test_real_planner_returns_plan_and_persists_turn(skip_without_key: None) -> None:
    from orchestrator.persistence import OrchestratorPersistence
    from planner.agent import PlannerAgent
    from planner.models import Plan
    from platform_db.models import AgentTurn
    from platform_db.repositories import sessions, tasks
    from platform_db.session import session_factory
    from sqlalchemy import select

    # A small, self-contained task so the model doesn't wander.
    task_description = "add a hasPermission(user, action) helper to the auth module"

    async with session_factory()() as db:
        task = await tasks.create(
            db, repo="demo-lib", title="int-test", description=task_description
        )
        await db.commit()
        task_id = task.id

    async with session_factory()() as db:
        task_session = await sessions.create(db, task_id=task_id, phase="plan")
        await db.commit()
        session_id: uuid.UUID = task_session.id

    persistence = OrchestratorPersistence()
    agent = PlannerAgent(recorder=persistence.record_agent_turn)

    plan = await agent.plan(task_description, session_id)

    assert isinstance(plan, Plan)
    assert plan.subtasks, "planner produced an empty subtask list"

    async with session_factory()() as db:
        turns_rows = (
            await db.execute(select(AgentTurn).where(AgentTurn.session_id == session_id))
        ).scalars().all()

    assert len(turns_rows) == 1
    turn = turns_rows[0]
    assert turn.agent == "planner"
    assert turn.model  # e.g. "claude-opus-4-7"
    assert turn.prompt_version.startswith("planner/plan@")
    assert turn.input_tokens > 0
    assert turn.output_tokens > 0
    assert turn.cost_usd is not None and turn.cost_usd > 0
