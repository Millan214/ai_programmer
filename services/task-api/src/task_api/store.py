"""Persistence seam for the task API.

Routes depend on the ``TaskStore`` protocol, not ``platform_db`` directly — so unit
tests inject an in-memory fake (the DB models use Postgres-only column types that don't
run on SQLite) while the deployed API uses ``PostgresTaskStore``. Mirrors the
orchestrator's ``PersistenceProtocol`` pattern.

``get_task`` reads three rows (task, its latest session, that session's latest verifier
run) in one DB session. Sequential queries rather than a single SQL join: three indexed
point/latest lookups are plenty for Phase 0, and the shape is easier to follow.
"""

import uuid
from decimal import Decimal
from typing import Protocol

from platform_db.models import VerifierRun
from platform_db.repositories import sessions, tasks, verifier_runs
from platform_db.session import session_factory

from task_api.schemas import TaskListItem, TaskStatusResponse, VerifierSummary


class TaskStore(Protocol):
    async def create_task(
        self, *, repo: str, title: str, description: str, budget_usd: float | None
    ) -> uuid.UUID: ...

    async def get_task(self, task_id: uuid.UUID) -> TaskStatusResponse | None: ...

    async def list_tasks(self, *, limit: int, offset: int) -> list[TaskListItem]: ...


class PostgresTaskStore:
    async def create_task(
        self, *, repo: str, title: str, description: str, budget_usd: float | None
    ) -> uuid.UUID:
        async with session_factory()() as db:
            budget = Decimal(str(budget_usd)) if budget_usd is not None else None
            task = await tasks.create(
                db,
                repo=repo,
                title=title,
                description=description,
                budget_usd=budget,
                status="queued",
            )
            await db.commit()
            return task.id

    async def get_task(self, task_id: uuid.UUID) -> TaskStatusResponse | None:
        async with session_factory()() as db:
            task = await tasks.get(db, task_id)
            if task is None:
                return None
            phase: str | None = None
            verifier: VerifierSummary | None = None
            latest_session = await sessions.latest_for_task(db, task_id)
            if latest_session is not None:
                phase = latest_session.phase
                run = await verifier_runs.latest_for_session(db, latest_session.id)
                if run is not None:
                    verifier = _summarize(run)
            return TaskStatusResponse(
                task_id=task.id,
                repo=task.repo,
                title=task.title,
                status=task.status,
                phase=phase,
                verifier=verifier,
                created_at=task.created_at,
            )

    async def list_tasks(self, *, limit: int, offset: int) -> list[TaskListItem]:
        async with session_factory()() as db:
            rows = await tasks.list_recent(db, limit=limit, offset=offset)
            return [
                TaskListItem(
                    task_id=task.id,
                    repo=task.repo,
                    title=task.title,
                    status=task.status,
                    created_at=task.created_at,
                )
                for task in rows
            ]


def _status_of(field: dict[str, object] | None) -> str | None:
    if not isinstance(field, dict):
        return None
    value = field.get("status")
    return value if isinstance(value, str) else None


def _summarize(run: VerifierRun) -> VerifierSummary:
    return VerifierSummary(
        build=_status_of(run.build),
        typecheck=_status_of(run.typecheck),
        tests=_status_of(run.tests),
        lint=_status_of(run.lint),
    )
