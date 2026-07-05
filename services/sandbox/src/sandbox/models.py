"""Data shapes exchanged between the sandbox controller and its HTTP surface."""

from pathlib import Path

from pydantic import BaseModel


class SandboxHandle(BaseModel):
    id: str
    worktree_path: Path
    container_id: str


class ExecResult(BaseModel):
    exit_code: int
    stdout: str
    stderr: str
