# Task 01 — Postgres schema + Alembic migrations

## Context

Everything the platform does gets persisted. Tasks, agent turns, verifier runs, sessions. Without this, nothing else can be built — the orchestrator can't checkpoint, agents can't record their work, and the smoke test has nothing to assert against. This card establishes the persistence foundation.

Read ADR-0001 before starting.

## Prereqs

- Scaffold complete (`make check` green on the empty repo).
- Postgres reachable via `make up`.

## Scope

Files to create in `packages/db/`:

- `src/platform_db/models.py` — SQLAlchemy declarative models for:
  - `task(id UUID, tenant_id UUID nullable, repo TEXT, title TEXT, description TEXT, status TEXT, budget_usd NUMERIC, cost_usd NUMERIC, created_at, closed_at nullable)`
  - `task_session(id UUID, task_id UUID FK, phase TEXT, supervisor_state JSONB, started_at, ended_at nullable)`
  - `agent_turn(id UUID, session_id UUID FK, agent TEXT, model TEXT, prompt_version TEXT, input_tokens INT, output_tokens INT, cost_usd NUMERIC, tool_calls JSONB, output_ref TEXT, created_at)`
  - `verifier_run(id UUID, session_id UUID FK, worktree_ref TEXT, build JSONB, typecheck JSONB, tests JSONB, coverage JSONB, lint JSONB, scanners JSONB, created_at)`
- `src/platform_db/session.py` — async engine + `AsyncSession` factory. Reads DB URL from env.
- `src/platform_db/repositories/` — one file per entity: `tasks.py`, `sessions.py`, `turns.py`, `verifier_runs.py`. Each exposes `create`, `get`, `update_status` etc. Repository pattern, not raw queries in callers.
- `alembic/env.py` — points at `models.Base.metadata`.
- `alembic/versions/0001_initial.py` — the four tables.
- `tests/test_models.py` — instantiate each model, assert basic invariants.
- `tests/test_repositories.py` — integration test: create task, add session, add turn, query back. Requires `make up`. Marked `@pytest.mark.integration`.

## Success criteria

```bash
cd packages/db
alembic upgrade head                   # exit 0
pytest -q                              # exit 0 (unit tests)
pytest -q -m integration               # exit 0 (with make up running)
alembic downgrade base && alembic upgrade head  # round-trip works
```

From the repo root: `make check && make test` still green.

## Non-goals

- **No `review`, `pr`, `adr`, `policy_decision` tables yet.** Those land in Phase 2 (`review`, `pr`) and later.
- **No multi-tenant enforcement.** `tenant_id` is nullable for now; enforcement is Phase 3.
- **No JSON schema validation on the JSONB columns.** Pydantic models around them come with the services that write them.
- **No connection pooling tuning.** Defaults are fine at Phase 0 scale.
- **No `create_all()`.** Alembic from day one.

## Effort

~2 hours.

## Notes

- IDs use a Python-side `default=uuid.uuid4` on `mapped_column`, not a DB-side `gen_random_uuid()`.
  Avoids depending on the `pgcrypto` extension in Phase 0. Consequence: a `Task()` etc. instance
  has `id is None` until it's flushed to a session — don't assert on `.id` before `flush()`.
- Repository functions take an `AsyncSession` as the first arg and `flush()` but never `commit()`.
  Callers (the orchestrator, later) own the transaction boundary.
- **Windows gotcha:** psycopg's async mode refuses to run under the default Windows
  `ProactorEventLoop` (raises `InterfaceError`). Fixed in `packages/db/tests/conftest.py` via
  `pytest_asyncio_loop_factories` → `SelectorEventLoop`, scoped to this package's tests only —
  deliberately not forced globally in `platform_db/session.py`, since card 06 (Docker sandbox)
  will likely need Proactor for async subprocess support on Windows dev machines. Any
  Windows-hosted service that mixes DB async calls with subprocess async calls will need to
  reconcile this; flag it when 06 lands.
- `pytest -q` run from `packages/db/` resolves its ini config from the **root** `pyproject.toml`
  (pytest walks up until it finds one, and `packages/db` doesn't define its own
  `[tool.pytest.ini_options]`), so it actually collects tests repo-wide via the root `testpaths`,
  not just this package. Not introduced by this card — inherited from the scaffold — but worth
  knowing if `pytest -q` from a subpackage ever looks like it ran "too many" tests.
