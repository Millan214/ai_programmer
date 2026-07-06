"""Fire-and-forget orchestrator launch.

POST /tasks returns as soon as the row is written; the run itself proceeds in a
background asyncio task. The strong reference in ``_background`` keeps the task alive
(``asyncio.create_task`` only holds a weak one, so without this the GC can cancel an
in-flight run), and the done-callback both drops that reference and surfaces a crash
instead of letting it vanish into an un-awaited task.

Phase 0 runs in-process — fine for a single-node demo. A durable queue (the run
surviving an API restart) is a Phase 1+ concern. ``launch`` is the seam unit tests
replace so they never spin up a real orchestrator.
"""

import asyncio
import uuid

_background: set[asyncio.Task[None]] = set()


async def _run(task_id: uuid.UUID) -> None:
    # Imported lazily so importing the API (and its tests) doesn't drag in the whole
    # orchestrator/agent stack at module load.
    from orchestrator.main import run

    await run(task_id)


def launch(task_id: uuid.UUID) -> None:
    task = asyncio.create_task(_run(task_id))
    _background.add(task)
    task.add_done_callback(_on_done)


def _on_done(task: "asyncio.Task[None]") -> None:
    _background.discard(task)
    if not task.cancelled():
        # Re-raise-into-view: reading the exception marks it retrieved; we log via the
        # exception's repr since structlog isn't wired yet (R4). Swallowing is deliberate
        # — a failed run is recorded on the task row by the orchestrator itself.
        exc = task.exception()
        if exc is not None:
            print(f"orchestrator run failed: {exc!r}")
