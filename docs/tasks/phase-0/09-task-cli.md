# Task 09 — Task submission CLI + HTTP API

## Context

Humans need a way to submit tasks. The API is also what CI, Slack, and future UIs call. Thin wrapper: create a task row, enqueue orchestrator run, return task ID. Status polling is a GET.

## Prereqs

- Task 03 (orchestrator).

## Scope

Files to create in `services/task-api/`:

- `src/task_api/schemas.py` — Pydantic request/response models: `CreateTaskRequest`, `TaskResponse`, `TaskStatusResponse`.
- `src/task_api/routes.py`:
  - `POST /tasks` body `{repo: str, title: str, description: str, budget_usd?: float}` → creates task row, spawns orchestrator run (asyncio task), returns `{task_id, status: "queued"}`.
  - `GET /tasks/{task_id}` → returns task row + latest session + latest verifier run (joined query).
  - `GET /tasks` → paginated list, most recent first.
- `src/task_api/main.py` — FastAPI app, uvicorn entrypoint.
- `src/task_api/cli.py` — Click-based CLI wrapping the API:
  - `platform-cli submit --repo demo-lib --title "..." --description "..."` → POST /tasks, print task_id.
  - `platform-cli status <task_id>` → GET, print human-readable status.
  - `platform-cli list [--limit N]` → GET /tasks, print table.
  - Reads API URL from `PLATFORM_API_URL` env, default `http://localhost:8000`.
- Add `[project.scripts]` entry for `platform-cli` in `pyproject.toml`.
- `tests/test_routes.py`:
  - POST creates a task, response includes valid UUID.
  - GET returns the task; nonexistent ID returns 404.
  - Orchestrator run is invoked (mocked in unit test).
- `tests/test_cli.py`:
  - Click test runner: submit → status → list. All three exit 0 and print expected output. Mocked HTTP.

## Success criteria

```bash
cd services/task-api
pytest -q                              # exit 0

# Run the API + orchestrator services.
make up  # postgres, jaeger
uvicorn task_api.main:app --port 8000 &

# Submit a task.
platform-cli submit --repo demo-lib \
  --title "add hasPermission helper" \
  --description "Add a hasPermission(user, action) function in src/perms.ts with unit tests."
# → prints task_id: abc-123

platform-cli status abc-123
# → prints current phase and status.

platform-cli list --limit 5
# → prints table with the submitted task at the top.
```

## Non-goals

- **No auth.** Any local client can submit. Auth lands in Phase 3.
- **No quotas or rate limiting.** Phase 3.
- **No multi-tenant fields in the request.** Phase 3.
- **No task cancellation.** GET only; no DELETE. Phase 2.
- **No webhook / streaming updates.** Polling only. WebSocket / SSE is a Phase 2 nice-to-have.
- **No task retries via the API.** Manual re-submit if a task fails.

## Effort

~2 hours.

## Notes

- **`TaskStore` seam over `platform_db`.** Routes depend on a `TaskStore` protocol, not
  the DB repos directly, so unit tests inject an in-memory fake. The models use
  Postgres-only column types (`UUID`, `JSONB`) that don't run on SQLite, so there's no
  cheap in-process DB for unit tests — the protocol seam is how the route tests stay
  unit-fast. `PostgresTaskStore` is the real impl; `test_routes_integration.py` covers it
  against `make up`.
- **Background run via `runner.launch`.** POST enqueues the orchestrator with
  `asyncio.create_task`, holding a strong reference so the GC can't cancel an in-flight
  run, with a done-callback that surfaces (not swallows) a crash. `launch` is a module
  attribute the tests monkeypatch so no real orchestrator spins up. Phase 0 is in-process;
  a durable queue that survives an API restart is Phase 1+.
- **Three sequential reads, not a SQL join.** `GET /tasks/{id}` reads task → latest session
  → latest verifier run in one session. Added `tasks.list_recent`, `sessions.latest_for_task`,
  `verifier_runs.latest_for_session` to `platform_db` (query helpers only — no schema
  change). FK indexes (review finding R14) would speed these; not done here.
- **Ruff config:** added `flake8-bugbear.extend-immutable-calls` for `fastapi.Depends`/
  `fastapi.Query` so B008 (mutable default) doesn't fire on the idiomatic DI pattern —
  the first routes in the repo to use `Depends` in argument defaults.
- **New task status `queued`.** The API writes `status="queued"` on create; the
  orchestrator overwrites it (`completed`/`failed_verify`) as the run progresses. Status
  strings are still free-form (R14's CHECK-constraint note applies).
