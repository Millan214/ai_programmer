import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from platform_db.models import VerifierRun


async def create(
    session: AsyncSession,
    *,
    session_id: uuid.UUID,
    worktree_ref: str,
    build: dict[str, object] | None = None,
    typecheck: dict[str, object] | None = None,
    tests: dict[str, object] | None = None,
    coverage: dict[str, object] | None = None,
    lint: dict[str, object] | None = None,
    scanners: dict[str, object] | None = None,
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
