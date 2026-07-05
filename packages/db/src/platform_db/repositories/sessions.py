import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from platform_db.models import TaskSession


async def create(
    session: AsyncSession,
    *,
    task_id: uuid.UUID,
    phase: str,
    supervisor_state: dict[str, object] | None = None,
) -> TaskSession:
    task_session = TaskSession(task_id=task_id, phase=phase, supervisor_state=supervisor_state)
    session.add(task_session)
    await session.flush()
    return task_session


async def get(session: AsyncSession, session_id: uuid.UUID) -> TaskSession | None:
    return await session.get(TaskSession, session_id)


async def update_phase(session: AsyncSession, session_id: uuid.UUID, phase: str) -> None:
    task_session = await session.get(TaskSession, session_id)
    if task_session is None:
        raise ValueError(f"task_session {session_id} not found")
    task_session.phase = phase
    await session.flush()
