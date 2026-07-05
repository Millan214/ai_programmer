"""Domain persistence for a task run: task_session + agent_turn rows.

ADR-0001 calls for a LangGraph checkpointer backed by Postgres. A conformant
``BaseCheckpointSaver`` needs a ``checkpoints`` table, which the card-01 schema does not
define (and card 01 owns the schema — no ad-hoc tables). So Phase 0 splits the concern:
the graph uses LangGraph's in-memory ``MemorySaver`` for run-local checkpointing, while
this module writes the *auditable* rows the platform actually queries — one ``task_session``
per run, one ``agent_turn`` per node transition. The DB-backed checkpointer is deferred to
a follow-up card.

Real agents (card 04's Planner and onward) write their own ``agent_turn`` rows through
``record_agent_turn`` so the row carries the true model/tokens/cost. Phases whose agent
still fakes it (build/verify/ship in Phase 0) go through ``record_node``, which writes a
placeholder turn. Either way the graph advances the task_session phase via
``advance_phase`` — ``record_node`` folds that call in so the fake paths stay tight.
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

    async def advance_phase(self, session_id: uuid.UUID, phase: str) -> None: ...

    async def record_node(
        self, session_id: uuid.UUID, phase: str, agent: str, output_ref: str | None = None
    ) -> None: ...

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

    async def advance_phase(self, session_id: uuid.UUID, phase: str) -> None:
        async with session_factory()() as db:
            await sessions.update_phase(db, session_id, phase)
            await db.commit()

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
        async with session_factory()() as db:
            await turns.create(
                db,
                session_id=session_id,
                agent=agent,
                model=model,
                prompt_version=prompt_version,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                tool_calls=tool_calls,
                output_ref=output_ref,
            )
            await db.commit()

    async def set_task_status(self, task_id: uuid.UUID, status: str) -> None:
        async with session_factory()() as db:
            await tasks.update_status(db, task_id, status)
            await db.commit()
