# Task 11 — End-to-end smoke test

## Context

The Phase 0 exit criterion, made executable. This test proves the whole loop works: submit a well-scoped task, agents run against the demo repo, Verifier passes, a fake PR reference is written, and Postgres has an auditable trail. Anything short of green here means Phase 0 isn't done.

## Prereqs

- Tasks 01–10 all complete.
- Demo repo at `target-repos/demo-lib/` with Graphify + CRG indexed.
- Anthropic API key.

## Scope

Files to create in `tests/e2e/`:

- `test_hello_world_task.py`:
  - Session-scoped fixture spins up all services via `docker compose up` (postgres, jaeger) plus starts each Python service as a subprocess.
  - Session-scoped fixture prepares a clean git branch on demo-lib.
  - The test itself:
    1. Submits a task via `POST /tasks`: title `"add hasPermission helper"`, description spelling out a small, well-scoped change (function signature, file location, one test case).
    2. Polls `GET /tasks/{id}` every 5s, up to 5 minutes.
    3. Asserts task status ends `completed`.
    4. Asserts a `verifier_run` row exists with `build.status="pass"` and `tests.status="pass"`.
    5. Asserts `agent_turn` rows exist for planner (1 row) and developer (>=1 row).
    6. Asserts the total cost recorded on the task is <$2 (Phase 0 sanity budget).
    7. Asserts the diff on the sandbox worktree contains the expected file (`src/perms.ts` or similar) and a test file.
- `test_verifier_failure_terminates.py`:
  - Same setup, but submits a task designed to fail Verifier (e.g. deliberately impossible constraint).
  - Asserts task ends `failed_verify` and does not reach ship phase.
- `conftest.py` — shared fixtures.
- `Makefile` target: `test-e2e` that runs these with a longer timeout.
- CI: a separate GitHub Actions workflow `.github/workflows/nightly-e2e.yml` that runs `make test-e2e` nightly with `ANTHROPIC_API_KEY` secret.

## Success criteria

```bash
# Local run:
make up
export ANTHROPIC_API_KEY=...
make test-e2e
# Both tests pass. Takes 2-5 minutes.

# CI:
# The nightly-e2e workflow shows green on main.
```

Additionally, opening Jaeger during a run shows a complete trace tree for each task.

## Non-goals

- **No performance assertions beyond the $2 cap.** Latency benchmarking is Phase 3.
- **No parallel task testing.** Merge coordinator (Phase 1) is a prerequisite for parallelism.
- **No cross-repo tests.** Single demo repo.
- **No LLM output quality assertions beyond "verifier passes".** Reviewer-quality tests are Phase 2.
- **No flake retries.** If the test flakes, fix the cause. Don't paper over with retries.
- **No load testing.** Single task at a time.
- **No security scanning of the produced diff.** Phase 2.

## Effort

~3 hours (test itself is small; harness setup and debugging the first end-to-end run is where the time goes).

## When this passes

Phase 0 is done. Merge to main, tag `v0.1.0-phase0`, and move to Phase 1 planning. Before writing Phase 1 task cards, re-read every `## Notes` section across Phase 0 cards — those notes are the highest-signal input to Phase 1 scope.

## Notes

_(fill in as you go — including what surprised you about how the full loop behaved end-to-end)_
