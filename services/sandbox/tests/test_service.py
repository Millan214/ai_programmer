"""HTTP surface tests — monkeypatch the controller so these don't need Docker.

Real spawn/exec/diff/destroy behavior is covered by ``test_controller.py``'s
integration tests.
"""

# httpx's ``Client.post``/``.get``/``.delete`` return type doesn't fully resolve under
# pyright strict, so `response` and everything derived from it comes back as Unknown;
# the assertions below are the actual type check.
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sandbox.controller import SandboxError
from sandbox.models import ExecResult, SandboxHandle
from sandbox.service import app

client = TestClient(app)


def _stub_handle(task_id: UUID) -> SandboxHandle:
    return SandboxHandle(
        id=str(task_id),
        worktree_path=Path("/tmp/sandbox") / str(task_id),
        container_id="abc123",
    )


def test_create_sandbox_rejects_missing_repo_path() -> None:
    response = client.post("/sandboxes", json={"repo_path": "/does/not/exist"})
    assert response.status_code == 400


def test_full_round_trip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    task_id = uuid4()
    handle = _stub_handle(task_id)

    forwarded_setup: list[list[list[str]] | None] = []

    async def fake_spawn(
        repo_path: Path,
        task_id_arg: UUID,
        setup_commands: list[list[str]] | None = None,
    ) -> SandboxHandle:
        forwarded_setup.append(setup_commands)
        return handle

    async def fake_exec(h: SandboxHandle, command: list[str], timeout_s: int = 300) -> ExecResult:
        assert h.id == handle.id
        return ExecResult(exit_code=0, stdout="ok\n", stderr="")

    async def fake_get_diff(h: SandboxHandle) -> str:
        return "diff --git a/x b/x\n"

    destroyed: list[str] = []

    async def fake_destroy(h: SandboxHandle) -> None:
        destroyed.append(h.id)

    monkeypatch.setattr("sandbox.service.spawn", fake_spawn)
    monkeypatch.setattr("sandbox.service.exec", fake_exec)
    monkeypatch.setattr("sandbox.service.get_diff", fake_get_diff)
    monkeypatch.setattr("sandbox.service.destroy", fake_destroy)

    response = client.post(
        "/sandboxes",
        json={
            "repo_path": str(tmp_path),
            "task_id": str(task_id),
            "setup_commands": [["pnpm", "install"]],
        },
    )
    assert response.status_code == 200
    created = SandboxHandle.model_validate(response.json())
    assert created.container_id == "abc123"
    assert forwarded_setup == [[["pnpm", "install"]]]

    response = client.post(f"/sandboxes/{created.id}/exec", json={"command": ["echo", "ok"]})
    assert response.status_code == 200
    assert ExecResult.model_validate(response.json()).stdout == "ok\n"

    response = client.get(f"/sandboxes/{created.id}/diff")
    assert response.status_code == 200
    assert "diff --git" in response.json()["diff"]

    response = client.delete(f"/sandboxes/{created.id}")
    assert response.status_code == 200
    assert destroyed == [created.id]


def test_exec_unknown_sandbox_returns_404() -> None:
    response = client.post("/sandboxes/does-not-exist/exec", json={"command": ["echo", "hi"]})
    assert response.status_code == 404


def test_spawn_failure_returns_502(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    async def fake_spawn(
        repo_path: Path,
        task_id_arg: UUID,
        setup_commands: list[list[str]] | None = None,
    ) -> SandboxHandle:
        raise SandboxError("git worktree add failed: boom")

    monkeypatch.setattr("sandbox.service.spawn", fake_spawn)

    response = client.post("/sandboxes", json={"repo_path": str(tmp_path)})
    assert response.status_code == 502
