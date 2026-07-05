"""The Sandbox controller's FastAPI surface.

``POST /sandboxes``, ``POST /sandboxes/{id}/exec``, ``GET /sandboxes/{id}/diff``,
``DELETE /sandboxes/{id}``. Handles are kept in-process (single controller instance,
Phase 0 scale — see 06-sandbox-docker.md's non-goals).
"""

from pathlib import Path
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from sandbox.controller import SandboxError, destroy, exec, get_diff, spawn
from sandbox.models import ExecResult, SandboxHandle

app = FastAPI(title="Sandbox Controller")

_handles: dict[str, SandboxHandle] = {}


class SpawnRequest(BaseModel):
    repo_path: str
    task_id: UUID | None = None


class ExecRequest(BaseModel):
    command: list[str]
    timeout_s: int = 300


class DiffResponse(BaseModel):
    diff: str


def _get_handle(sandbox_id: str) -> SandboxHandle:
    handle = _handles.get(sandbox_id)
    if handle is None:
        raise HTTPException(status_code=404, detail=f"unknown sandbox: {sandbox_id}")
    return handle


@app.post("/sandboxes")
async def create_sandbox(request: SpawnRequest) -> SandboxHandle:
    repo_path = Path(request.repo_path)
    if not repo_path.is_dir():
        raise HTTPException(status_code=400, detail=f"repo_path does not exist: {repo_path}")
    task_id = request.task_id or uuid4()
    try:
        handle = await spawn(repo_path, task_id)
    except SandboxError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    _handles[handle.id] = handle
    return handle


@app.post("/sandboxes/{sandbox_id}/exec")
async def exec_in_sandbox(sandbox_id: str, request: ExecRequest) -> ExecResult:
    handle = _get_handle(sandbox_id)
    try:
        return await exec(handle, request.command, timeout_s=request.timeout_s)
    except SandboxError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/sandboxes/{sandbox_id}/diff")
async def diff_sandbox(sandbox_id: str) -> DiffResponse:
    handle = _get_handle(sandbox_id)
    try:
        diff = await get_diff(handle)
    except SandboxError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return DiffResponse(diff=diff)


@app.delete("/sandboxes/{sandbox_id}")
async def delete_sandbox(sandbox_id: str) -> None:
    handle = _get_handle(sandbox_id)
    await destroy(handle)
    del _handles[sandbox_id]
