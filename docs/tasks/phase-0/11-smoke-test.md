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

- **Status: harness complete and validated up to the LLM loop; not yet run green
  end-to-end.** A real green run needs a Linux host + `ANTHROPIC_API_KEY` (see the Windows
  note below). What *was* validated locally on Windows with Docker running: `docker compose
  up postgres`, `alembic upgrade head` (schema lands), the sandbox image build, the sync
  `_db.py` reader against the live DB, and both a real service (`verifier`) and the stub
  MCP booting under uvicorn and passing the `/openapi.json` health check. The only
  unexercised leg is the actual submit → agents → verify loop.
- **Graphify/CRG prereq was never built.** The card lists "demo repo with Graphify + CRG
  indexed" as a prereq, but Phase 0 only built the *client* wrappers (card 07), not the
  servers. `tests/e2e/stub_mcp.py` serves the `/tools/{tool}` contract with empty results
  so retrieval succeeds-but-returns-nothing; the smoke task names its files/signatures
  explicitly, so the Developer works from the plan/repo-map hints. Standing up real
  Graphify + CRG is Phase 1.
- **Assertion 7 needed diff persistence.** Nothing stored the produced diff — it lived only
  in the in-memory `edits` dict and the sandbox worktree (destroyed at end of run). So the
  Developer now persists its final diff on a zero-token `agent_turn.output_ref` at
  `_finish` (with `tool_calls={"final_status": ...}`). This makes the work product
  auditable and gives the e2e something to assert on. (Small card-08 follow-up; unit tests
  updated for the extra turn.)
- **Cost assertion reads `agent_turn`, not `task.cost_usd`.** Phase 0 never rolls cost up
  onto the task row, so the $2 check sums `agent_turn.cost_usd` across the run's sessions.
  Rolling cost onto the task (and a CHECK-constrained status enum, R14) is Phase 1+.
- **Failure test is deterministic by construction.** Rather than hope the model produces a
  failure, `test_verifier_failure_terminates` asks it to create a file with a literal
  `expect(1).toBe(2)` vitest test — copy-paste explicit, so the Verifier goes red reliably
  and the run ends `failed_verify` without shipping. (Honors "no flake retries".)
- **Jaeger is best-effort in the harness.** The tests don't assert on traces, and a host
  may already own the OTLP port (this dev box runs signoz on 4317). So the infra fixture
  requires Postgres but tolerates Jaeger failing to start — a missing trace backend
  shouldn't fail a smoke test, and `configure()` is offline-safe anyway.
- **Windows can't run this green; Linux/CI can.** Two host-specific breaks: (1) psycopg's
  async driver needs a selector event loop, but uvicorn on Windows uses the proactor loop,
  so DB-touching requests fail at runtime; (2) the sandbox installs `node_modules` *inside*
  a Linux container while the Verifier runs on the *host* — on Windows those are different
  platforms and the Linux-built native binaries (esbuild/vitest) won't execute host-side.
  Both vanish on Linux (host and container agree), which is where `nightly-e2e.yml` runs.
- **When it goes green:** per the card, re-read every Phase 0 `## Notes` section before
  scoping Phase 1 — the running list of deviations and deferred items (R1–R18 review
  findings, the Graphify/CRG gap, host-vs-container verifier, cost roll-up) is the
  highest-signal input.
