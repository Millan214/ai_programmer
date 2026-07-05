# platform-sandbox

Docker-based sandbox controller for isolated task execution (ADR-0003, Phase 0 backend;
Firecracker is Phase 1).

Each sandbox is a git worktree checked out from the target repo, bind-mounted into a
long-lived Docker container (`platform-sandbox:phase0`, Node 20 + pnpm + git). The
controller (`sandbox.controller`) spawns, execs into, diffs, and tears down that
container/worktree pair; `sandbox.service` exposes the same operations over HTTP.

## Build the image

```bash
docker build -t platform-sandbox:phase0 src/sandbox/
```

## Run the tests

```bash
pytest -q                    # unit tests, no Docker required
pytest -q -m integration      # spawns real containers/worktrees — requires Docker daemon
```

Filled in by [`06-sandbox-docker.md`](../../docs/tasks/phase-0/06-sandbox-docker.md).
