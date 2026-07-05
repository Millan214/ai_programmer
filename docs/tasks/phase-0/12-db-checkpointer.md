# Task 12 — Postgres-backed LangGraph checkpointer

## Context

Spawned by task 03. ADR-0001 calls for graph state to be persisted via LangGraph's
checkpointer, backed by our own Postgres (not the built-in SQLite/in-memory savers), so
that a task is resumable after a process restart. Task 03 shipped the outer FSM with
LangGraph's in-memory `MemorySaver` instead, because a conformant checkpointer needs a
`checkpoints` table that the card-01 schema doesn't define, and task 03 was not the place
to change the schema. This card closes that gap.

Until this lands, the platform's auditable state (`task_session`, `agent_turn`) is durable,
but LangGraph's own graph checkpoints are not — a mid-run process crash cannot be resumed
from the last node; the task must be re-run from the start.

Read ADR-0001 before starting.

## Prereqs

- Task 01 (owns the schema — this card adds a table via Alembic).
- Task 03 (orchestrator skeleton — this card swaps `MemorySaver` for the real saver).

## Scope

- New Alembic migration in `packages/db/alembic/versions/` adding the checkpoint tables
  LangGraph's Postgres saver expects (`checkpoints`, `checkpoint_writes`, `checkpoint_blobs`
  — confirm exact shape against the `langgraph-checkpoint-postgres` schema for the pinned
  LangGraph version).
- Evaluate `langgraph-checkpoint-postgres` (`AsyncPostgresSaver`) vs. a hand-rolled
  `BaseCheckpointSaver`. Prefer the official package if its schema and async API fit our
  `platform_db` engine; document the call.
- `services/orchestrator/src/orchestrator/persistence.py` or a new `checkpointer.py`:
  construct the async saver from the same DB URL as `platform_db.session`.
- `services/orchestrator/src/orchestrator/graph.py`: replace `MemorySaver()` in
  `build_graph` with the injected DB-backed saver (keep it injectable so unit tests can
  still pass an in-memory saver).
- Tests: an integration test that runs a task partway, drops the compiled graph, rebuilds
  it, and resumes from the checkpoint by `thread_id` — asserting the run completes without
  redoing already-finished nodes.

## Success criteria

```bash
cd packages/db && alembic upgrade head          # new checkpoint tables created
cd services/orchestrator
pytest -q                                        # exit 0 (unit; in-memory saver)
pytest -q -m integration                         # exit 0 (resume-from-checkpoint test)
```

`make check && make test` green from the repo root.

## Non-goals

- **No change to the outer FSM shape.** Same Plan/Build/Verify/Ship nodes.
- **No cross-process orchestration or a run queue.** Resumption is triggered by re-invoking
  with the same `thread_id`; a scheduler that detects and resumes orphaned runs is later.
- **No checkpoint GC/retention policy.** Pruning old checkpoints is a separate concern.

## Effort

~3 hours.

## Notes

_(fill in as you go)_
