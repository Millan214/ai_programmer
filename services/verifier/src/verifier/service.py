"""The Verifier's FastAPI surface: one endpoint, ``POST /verify``.

Owns no LLM (ADR-0006) — every field in :class:`VerifierResult` comes from a real
subprocess run, never inferred.
"""

import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from verifier.models import VerifierResult
from verifier.runners import pnpm

app = FastAPI(title="Verifier")


class VerifyRequest(BaseModel):
    worktree_path: str


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


@app.post("/verify")
async def verify_endpoint(request: VerifyRequest) -> VerifierResult:
    cwd = Path(request.worktree_path)
    if not cwd.is_dir():
        raise HTTPException(status_code=400, detail=f"worktree_path does not exist: {cwd}")
    return await verify(cwd)
