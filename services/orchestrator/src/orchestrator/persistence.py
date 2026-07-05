"""Domain persistence for a task run: task_session + agent_turn rows.

ADR-0001 calls for a LangGraph checkpointer backed by Postgres. A conformant
``BaseCheckpointSaver`` needs a ``checkpoints`` table, which the card-01 schema does not
define (and card 01 owns the schema — no ad-hoc tables). So Phase 0 splits the concern:
the graph uses LangGraph's in-memory ``MemorySaver`` for run-local checkpointing, while
this module writes the *auditable* rows the platform actually queries — one ``task_session``
per run, one ``agent_turn`` per node transition. The DB-backed checkpointer is deferred to
a follow-up card.

Token/cost fields are placeholder zeros in Phase 0 (non-goal: no cost tracking). Real
values arrive with the LLM-calling agents in cards 04 and 08.
"""

import uuid
from decimal import Decimal
from typing import Protocol, TypedDict

from platform_db.repositories import sessions, tasks, turns
from platform_db.session import session_factory

from orchestrator.state import DEFAULT_BUDGET_REMAINING

_PLACEHOLDER_MODEL = "fake"


class OrchestratorError(Exception):
    """Raised when a task run cannot proceed (e.g. the task row is missing)."""


class TaskInfo(TypedDict):
    description: str
    repo: str
    budget_remaining: float


class PersistenceProtocol(Protocol):
    """The orchestrator's entire persistence surface, injected for testability.

    Unit tests pass an in-memory fake; the integration path uses
    ``OrchestratorPersistence`` against Postgres.
    """

    async def load_task(self, task_id: uuid.UUID) -> TaskInfo: ...

    async def open_session(self, task_id: uuid.UUID) -> uuid.UUID: ...

    async def record_node(
        self, session_id: uuid.UUID, phase: str, agent: str, output_ref: str | None = None
    ) -> None: ...

    async def set_task_status(self, task_id: uuid.UUID, status: str) -> None: ...


class OrchestratorPersistence:
    """Postgres-backed persistence via the ``platform_db`` repositories."""

    async def load_task(self, task_id: uuid.UUID) -> TaskInfo:
        async with session_factory()() as db:
            task = await tasks.get(db, task_id)
            if task is None:
                raise OrchestratorError(f"task {task_id} not found")
            budget = (
                float(task.budget_usd)
                if task.budget_usd is not None
                else DEFAULT_BUDGET_REMAINING
            )
            return TaskInfo(
                description=task.description or "",
                repo=task.repo,
                budget_remaining=budget,
            )

    async def open_session(self, task_id: uuid.UUID) -> uuid.UUID:
        async with session_factory()() as db:
            task_session = await sessions.create(db, task_id=task_id, phase="plan")
            await db.commit()
            return task_session.id

    async def record_node(
        self, session_id: uuid.UUID, phase: str, agent: str, output_ref: str | None = None
    ) -> None:
        async with session_factory()() as db:
            await sessions.update_phase(db, session_id, phase)
            await turns.create(
                db,
                session_id=session_id,
                agent=agent,
                model=_PLACEHOLDER_MODEL,
                prompt_version=f"{agent}@fake",
                input_tokens=0,
                output_tokens=0,
                cost_usd=Decimal(0),
                tool_calls={},
                output_ref=output_ref,
            )
            await db.commit()

    async def set_task_status(self, task_id: uuid.UUID, status: str) -> None:
        async with session_factory()() as db:
            await tasks.update_status(db, task_id, status)
            await db.commit()
