import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from platform_db.models import VerifierRun


async def create(
    session: AsyncSession,
    *,
    session_id: uuid.UUID,
    worktree_ref: str,
    build: dict | None = None,
    typecheck: dict | None = None,
    tests: dict | None = None,
    coverage: dict | None = None,
    lint: dict | None = None,
    scanners: dict | None = None,
) -> VerifierRun:
    run = VerifierRun(
        session_id=session_id,
        worktree_ref=worktree_ref,
        build=build,
        typecheck=typecheck,
        tests=tests,
        coverage=coverage,
        lint=lint,
        scanners=scanners,
    )
    session.add(run)
    await session.flush()
    return run


async def get(session: AsyncSession, run_id: uuid.UUID) -> VerifierRun | None:
    return await session.get(VerifierRun, run_id)
