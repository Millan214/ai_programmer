import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from platform_db.models import Task


async def create(
    session: AsyncSession,
    *,
    repo: str,
    title: str,
    description: str | None = None,
    tenant_id: uuid.UUID | None = None,
    budget_usd: Decimal | None = None,
    status: str = "pending",
) -> Task:
    task = Task(
        repo=repo,
        title=title,
        description=description,
        tenant_id=tenant_id,
        budget_usd=budget_usd,
        status=status,
    )
    session.add(task)
    await session.flush()
    return task


async def get(session: AsyncSession, task_id: uuid.UUID) -> Task | None:
    return await session.get(Task, task_id)


async def update_status(session: AsyncSession, task_id: uuid.UUID, status: str) -> None:
    task = await session.get(Task, task_id)
    if task is None:
        raise ValueError(f"task {task_id} not found")
    task.status = status
    await session.flush()
