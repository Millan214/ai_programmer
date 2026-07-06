"""Docker + git-worktree sandbox controller (ADR-0003, Phase 0 backend).

Shells out to the ``git`` and ``docker`` CLIs rather than binding a client library,
matching the Verifier's runners (``verifier.runners.pnpm``): both tools are already
required on the host, and CLI output is what a human would see debugging by hand.
"""

import asyncio
from pathlib import Path
from uuid import UUID

from sandbox.models import ExecResult, SandboxHandle

IMAGE = "platform-sandbox:phase0"
SANDBOX_ROOT = Path("/tmp/sandbox")
# A named docker volume for pnpm's content-addressable store, shared across sandboxes so
# per-spawn dependency installs reuse downloads instead of hitting the network cold every
# time. Mounted at the container's default pnpm store path.
PNPM_STORE_VOLUME = "platform-pnpm-store"
_PNPM_STORE_PATH = "/root/.local/share/pnpm/store"
# Dependency install can be slow on a cold store; give setup its own generous ceiling
# rather than borrowing ``exec``'s per-command default.
_SETUP_TIMEOUT_S = 600


class SandboxError(Exception):
    """Raised when a git or docker operation backing the sandbox fails."""


async def _run(cmd: list[str], *, cwd: Path | None = None) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode or 0, stdout.decode(errors="replace"), stderr.decode(errors="replace")


async def _repo_root(worktree_path: Path) -> Path:
    """Resolve a linked worktree back to its main repo, so ``git worktree remove``
    (which must run from the main tree or another linked tree) has somewhere to run."""
    code, stdout, stderr = await _run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=worktree_path,
    )
    if code != 0:
        raise SandboxError(f"could not resolve repo root for {worktree_path}: {stderr.strip()}")
    return Path(stdout.strip()).parent


async def spawn(
    repo_path: Path,
    task_id: UUID,
    setup_commands: list[list[str]] | None = None,
) -> SandboxHandle:
    """Create a worktree + container for a task.

    ``setup_commands`` run in the container after it starts — Phase 0 uses this to
    install the target repo's dependencies (``pnpm install``), which a fresh
    ``git worktree add`` doesn't carry (only tracked files come across, no
    ``node_modules``). Without it the Verifier fails on a clean sandbox. Each command
    must exit 0; the first failure tears the sandbox down and raises, so a bad install
    never leaves a half-provisioned container behind.
    """
    worktree_path = SANDBOX_ROOT / str(task_id)
    SANDBOX_ROOT.mkdir(parents=True, exist_ok=True)

    code, _stdout, stderr = await _run(
        ["git", "worktree", "add", str(worktree_path)], cwd=repo_path
    )
    if code != 0:
        raise SandboxError(f"git worktree add failed: {stderr.strip()}")

    container_name = f"sandbox-{task_id}"
    code, stdout, stderr = await _run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            container_name,
            "-v",
            f"{worktree_path}:/workspace",
            "-v",
            f"{PNPM_STORE_VOLUME}:{_PNPM_STORE_PATH}",
            "-w",
            "/workspace",
            IMAGE,
            "tail",
            "-f",
            "/dev/null",
        ]
    )
    if code != 0:
        await _run(["git", "worktree", "remove", "--force", str(worktree_path)], cwd=repo_path)
        raise SandboxError(f"docker run failed: {stderr.strip()}")

    handle = SandboxHandle(
        id=str(task_id),
        worktree_path=worktree_path,
        container_id=stdout.strip(),
    )

    for command in setup_commands or []:
        code, stdout, stderr = await _run_with_timeout(
            ["docker", "exec", handle.container_id, *command], _SETUP_TIMEOUT_S
        )
        if code != 0:
            await destroy(handle)
            raise SandboxError(
                f"sandbox setup command {command} failed (exit {code}): "
                f"{(stdout + stderr).strip()[-2000:]}"
            )

    return handle


async def _run_with_timeout(cmd: list[str], timeout_s: int) -> tuple[int, str, str]:
    try:
        return await asyncio.wait_for(_run(cmd), timeout=timeout_s)
    except TimeoutError as exc:
        raise SandboxError(f"command timed out after {timeout_s}s: {cmd}") from exc


async def exec(handle: SandboxHandle, command: list[str], timeout_s: int = 300) -> ExecResult:
    try:
        code, stdout, stderr = await asyncio.wait_for(
            _run(["docker", "exec", handle.container_id, *command]),
            timeout=timeout_s,
        )
    except TimeoutError as exc:
        await _run(["docker", "kill", handle.container_id])
        raise SandboxError(
            f"command timed out after {timeout_s}s and the container was killed: {command}"
        ) from exc
    return ExecResult(exit_code=code, stdout=stdout, stderr=stderr)


async def get_diff(handle: SandboxHandle) -> str:
    code, stdout, stderr = await _run(["git", "diff", "HEAD"], cwd=handle.worktree_path)
    if code != 0:
        raise SandboxError(f"git diff failed: {stderr.strip()}")
    return stdout


async def destroy(handle: SandboxHandle) -> None:
    await _run(["docker", "rm", "-f", handle.container_id])
    repo_root = await _repo_root(handle.worktree_path)
    await _run(
        ["git", "worktree", "remove", "--force", str(handle.worktree_path)], cwd=repo_root
    )
