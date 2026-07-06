"""Controller unit tests that don't need Docker — the ``_run`` shell-out is patched so
we can pin the spawn/setup control flow (ordering, teardown-on-failure) deterministically.
The real container/worktree behavior is covered by ``test_controller.py``'s integration tests.
"""

from pathlib import Path
from uuid import uuid4

import pytest
from sandbox import controller
from sandbox.controller import SandboxError, spawn


class _FakeRun:
    """Scripts ``controller._run`` by command prefix, recording calls in order."""

    def __init__(self, results: dict[str, tuple[int, str, str]]) -> None:
        self._results = results
        self.calls: list[list[str]] = []

    async def __call__(self, cmd: list[str], *, cwd: Path | None = None) -> tuple[int, str, str]:
        self.calls.append(cmd)
        for prefix, result in self._results.items():
            if " ".join(cmd).startswith(prefix):
                return result
        return (0, "", "")


@pytest.mark.asyncio
async def test_setup_commands_run_in_container_after_spawn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeRun({"docker run": (0, "container-xyz", "")})
    monkeypatch.setattr(controller, "_run", fake)

    handle = await spawn(Path("/repo"), uuid4(), setup_commands=[["pnpm", "install"]])

    assert handle.container_id == "container-xyz"
    # The install ran via docker exec against the freshly-started container.
    assert ["docker", "exec", "container-xyz", "pnpm", "install"] in fake.calls
    # ...and only after the worktree and container existed.
    exec_idx = fake.calls.index(["docker", "exec", "container-xyz", "pnpm", "install"])
    run_idx = next(i for i, c in enumerate(fake.calls) if c[:2] == ["docker", "run"])
    assert exec_idx > run_idx


@pytest.mark.asyncio
async def test_failed_setup_tears_down_and_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeRun(
        {
            "docker run": (0, "container-xyz", ""),
            "docker exec container-xyz pnpm install": (1, "", "ERR_PNPM_NO_LOCKFILE"),
        }
    )
    monkeypatch.setattr(controller, "_run", fake)

    with pytest.raises(SandboxError, match="setup command"):
        await spawn(Path("/repo"), uuid4(), setup_commands=[["pnpm", "install"]])

    # destroy() ran: container force-removed and worktree removed.
    assert any(c[:3] == ["docker", "rm", "-f"] for c in fake.calls)
    assert any(c[:3] == ["git", "worktree", "remove"] for c in fake.calls)


@pytest.mark.asyncio
async def test_no_setup_commands_skips_exec(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeRun({"docker run": (0, "container-xyz", "")})
    monkeypatch.setattr(controller, "_run", fake)

    await spawn(Path("/repo"), uuid4())

    assert not any(c[:2] == ["docker", "exec"] for c in fake.calls)
