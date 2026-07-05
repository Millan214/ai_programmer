"""Integration tests for the sandbox controller — spawn real containers and worktrees.

Requires a running Docker daemon and the ``platform-sandbox:phase0`` image
(``docker build -t platform-sandbox:phase0 src/sandbox/``).
"""

import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest
from sandbox.controller import SandboxError, destroy, exec, get_diff, spawn

pytestmark = pytest.mark.integration


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "info"], capture_output=True, check=False).returncode == 0


@pytest.fixture
def demo_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "demo-repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "README.md").write_text("hello\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
    return repo


@pytest.mark.asyncio
async def test_spawn_exec_diff_destroy(demo_repo: Path) -> None:
    if not _docker_available():
        pytest.skip("Docker daemon not available")

    handle = await spawn(demo_repo, uuid4())
    try:
        assert handle.worktree_path.is_dir()
        assert handle.container_id

        result = await exec(handle, ["cat", "README.md"])
        assert result.exit_code == 0
        assert "hello" in result.stdout

        await exec(handle, ["sh", "-c", "echo world >> README.md"])
        diff = await get_diff(handle)
        assert "world" in diff
    finally:
        await destroy(handle)

    assert not handle.worktree_path.exists()


@pytest.mark.asyncio
async def test_exec_times_out_and_kills_container(demo_repo: Path) -> None:
    if not _docker_available():
        pytest.skip("Docker daemon not available")

    handle = await spawn(demo_repo, uuid4())
    try:
        with pytest.raises(SandboxError):
            await exec(handle, ["sleep", "10"], timeout_s=1)
    finally:
        await destroy(handle)
