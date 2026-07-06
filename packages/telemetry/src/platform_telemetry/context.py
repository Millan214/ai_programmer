"""Task-scoped context so nested spans pick up their ``task_id`` automatically.

A ``contextvar`` rather than a thread-local: the platform is async, and contextvars are
the ones that propagate correctly across ``await`` boundaries and into tasks spawned with
``asyncio.create_task``. Set it once at the top of a run (the orchestrator does this in
``run``); every ``@traced`` span underneath reads it without threading ``task_id`` through
call signatures.
"""

import uuid
from contextvars import ContextVar

_task_id: ContextVar[uuid.UUID | None] = ContextVar("platform_task_id", default=None)


def set_task_context(task_id: uuid.UUID) -> None:
    _task_id.set(task_id)


def get_task_context() -> uuid.UUID | None:
    return _task_id.get()
