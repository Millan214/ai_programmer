"""The Verifier's FastAPI surface: one endpoint, ``POST /verify``.

Owns no LLM (ADR-0006) — every field in :class:`VerifierResult` comes from a real
subprocess run, never inferred.

When the caller supplies a ``session_id``, the run is persisted as a ``verifier_run``
row before the response returns — the durable fact ledger ADR-0006 exists for. It's
done here rather than in each caller so the orchestrator's Verify node and the
Developer's in-loop calls both inherit it. Callers without a session (ad-hoc/manual
verification) get facts back without writing history.
"""

import asyncio
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from platform_db.repositories import verifier_runs
from platform_db.session import session_factory
from platform_telemetry import lifespan_for, traced
from pydantic import BaseModel

from verifier.models import VerifierResult
from verifier.runners import pnpm

app = FastAPI(title="Verifier", lifespan=lifespan_for("verifier"))


class VerifyRequest(BaseModel):
    worktree_path: str
    session_id: uuid.UUID | None = None


@traced("verifier.verify")
async def verify(cwd: Path) -> VerifierResult:
    build_result, typecheck_result, test_result, lint_result = await asyncio.gather(
        pnpm.build(cwd),
        pnpm.typecheck(cwd),
        pnpm.test(cwd),
        pnpm.lint(cwd),
    )
    return VerifierResult(
        build=build_result,
        typecheck=typecheck_result,
        tests=test_result,
        lint=lint_result,
    )


async def persist_run(session_id: uuid.UUID, worktree_path: Path, result: VerifierResult) -> None:
    async with session_factory()() as db:
        await verifier_runs.create(
            db,
            session_id=session_id,
            worktree_ref=str(worktree_path),
            build=result.build.model_dump(),
            typecheck=result.typecheck.model_dump(),
            tests=result.tests.model_dump(),
            lint=result.lint.model_dump(),
        )
        await db.commit()


@app.post("/verify")
async def verify_endpoint(request: VerifyRequest) -> VerifierResult:
    cwd = Path(request.worktree_path)
    if not cwd.is_dir():
        raise HTTPException(status_code=400, detail=f"worktree_path does not exist: {cwd}")
    result = await verify(cwd)
    if request.session_id is not None:
        await persist_run(request.session_id, cwd, result)
    return result
