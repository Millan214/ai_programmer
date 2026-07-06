# Task 06 — Docker sandbox v0 with git worktree

## Context

Agents execute code they wrote — running verifier, testing, invoking build tools. That execution must be isolated from the orchestrator's process and filesystem. Phase 0 uses Docker containers with git worktrees; Firecracker migration is a Phase 1 task. See ADR-0003.

## Prereqs

- Scaffold complete.

## Scope

Files to create in `services/sandbox/`:

- `src/sandbox/models.py`:
  - `class SandboxHandle(BaseModel): id: str; worktree_path: Path; container_id: str`
- `src/sandbox/controller.py`:
  - `async def spawn(repo_path: Path, task_id: UUID) -> SandboxHandle`:
    - Creates a git worktree at `/tmp/sandbox/<task_id>` from `repo_path`.
    - Starts a Docker container from a base image (Node 20 + pnpm, from a Dockerfile in this package).
    - Bind-mounts the worktree at `/workspace` inside the container.
    - Container runs a long-lived `tail -f /dev/null` so we can `docker exec` into it.
  - `async def exec(handle: SandboxHandle, command: list[str], timeout_s: int = 300) -> ExecResult`:
    - Runs `docker exec` with the command, returns stdout/stderr/exit_code.
    - Enforces timeout via `asyncio.wait_for`; on timeout, kills the container.
  - `async def get_diff(handle: SandboxHandle) -> str` — `git diff HEAD` inside the worktree.
  - `async def destroy(handle: SandboxHandle) -> None` — stop container, remove worktree.
- `src/sandbox/Dockerfile` — Node 20 base, pnpm pre-installed, git, minimal build tools. `/workspace` as workdir.
- `src/sandbox/main.py` — FastAPI wrapping controller: `POST /sandboxes`, `POST /sandboxes/{id}/exec`, `GET /sandboxes/{id}/diff`, `DELETE /sandboxes/{id}`.
- `tests/test_controller.py`:
  - `spawn` produces a running container with the worktree mounted (integration, requires Docker).
  - `exec` runs a command and returns output.
  - `exec` times out cleanly on a hanging command.
  - `get_diff` returns changes made inside the container.
  - `destroy` removes container and worktree.
- `tests/test_service.py` — HTTP endpoints round-trip through the same flow.

## Success criteria

```bash
cd services/sandbox
docker build -t platform-sandbox:phase0 src/sandbox/
pytest -q -m integration               # exit 0 (Docker daemon required)

# Integration with a real target repo:
python -c "
import asyncio
from pathlib import Path
from uuid import uuid4
from sandbox.controller import spawn, exec, get_diff, destroy

async def main():
    handle = await spawn(Path('/path/to/demo-lib'), uuid4())
    result = await exec(handle, ['pnpm', 'install'])
    print('install:', result.exit_code)
    result = await exec(handle, ['pnpm', 'test'])
    print('test:', result.exit_code)
    await destroy(handle)

asyncio.run(main())
"
# Both commands return exit 0.
```

## Non-goals

- **No Firecracker.** Phase 1.
- **No base-image snapshots for Python / Go / Rust.** Phase 1.
- **No secrets injection.** Sandbox never sees secrets in Phase 0 (or any phase, per ADR-0003).
- **No network policy.** Container has default network access. Egress control is Phase 3.
- **No concurrent sandbox limits.** Fine at Phase 0 scale (one task at a time).
- **No sandbox pool / warm containers.** Cold-start every time. Optimization is Phase 1.
- **No Verifier integration inside the sandbox.** Verifier runs on the host and points at the worktree path; sandbox integration is a design consideration for Phase 1.

## Effort

~4 hours.

## Notes

- Shelled out to the `git` and `docker` CLIs directly (`asyncio.create_subprocess_exec`),
  matching the Verifier's runner pattern, instead of adding the `docker` Python SDK as a
  dependency — one less library to pin, and CLI output is what a human debugging by hand
  would see.
- `destroy()` needs the sandbox's main repo path to run `git worktree remove`, but
  `SandboxHandle` (per the card's spec) only carries `worktree_path`/`container_id`/`id`.
  Resolved by shelling out to `git rev-parse --path-format=absolute --git-common-dir` from
  inside the worktree before removing it, rather than widening the handle model.
- `uv sync` (no flags) does not install workspace members as editable packages in this
  repo — `uv sync --all-packages` (what `make install` runs) does. Without it, every
  service's own tests fail to import (`ModuleNotFoundError`), not just sandbox's. Worth
  remembering when a fresh clone's tests mysteriously can't import the package under test.
- Added `src/sandbox/py.typed`, which was missing — without it, pyright treats the
  installed `sandbox` package as untyped (`reportMissingTypeStubs`) even though it ships
  inline types. `verifier` already had this marker; `sandbox` didn't.
- Docker daemon was not running in this dev environment, so `test_controller.py`'s two
  integration tests were verified to skip cleanly (`_docker_available()` guard) rather than
  run end-to-end. The image build and real spawn/exec/diff/destroy flow from the card's
  "Success criteria" section still need a manual pass wherever Docker Desktop (or an
  equivalent daemon) is actually running.
- **`setup_commands` added (card 08 follow-up).** `spawn` gained an optional
  `setup_commands` that run in the container after start — deterministic dependency
  install (`pnpm install`), since a fresh `git worktree add` carries no `node_modules` and
  the Verifier would otherwise fail on a clean sandbox. A failed command tears the sandbox
  down and raises. A shared `platform-pnpm-store` docker volume is mounted so installs
  reuse downloads across spawns. `test_controller_unit.py` covers the ordering and
  teardown-on-failure paths without Docker; the real install is exercised by card 08's
  integration test. The *what to install* lives in the developer adapter
  (`SANDBOX_SETUP_COMMANDS`), keeping the controller toolchain-agnostic.
