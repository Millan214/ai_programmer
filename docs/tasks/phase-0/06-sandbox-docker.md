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

_(fill in as you go)_
