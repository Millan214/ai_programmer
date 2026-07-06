# platform-task-api

The submission surface: an HTTP API plus the `platform-cli` command (card 09). Thin —
create a task row, enqueue the orchestrator run in the background, poll for status.

## HTTP

- `POST /tasks` `{repo, title, description, budget_usd?}` → creates the row, launches the
  run, returns `{task_id, status: "queued"}`.
- `GET /tasks/{id}` → task row + latest session phase + latest verifier run statuses.
- `GET /tasks?limit=&offset=` → recent tasks, newest first.

Run it: `uvicorn task_api.main:app --port 8000` (needs `make up` for Postgres).

## CLI

`platform-cli` talks to `PLATFORM_API_URL` (default `http://localhost:8000`):

```
platform-cli submit --repo demo-lib --title "..." --description "..."
platform-cli status <task_id>
platform-cli list --limit 5
```

## Layout

- `schemas.py` — request/response models. `store.py` — the `TaskStore` protocol +
  `PostgresTaskStore` (the seam unit tests fake, since the DB uses Postgres-only types).
- `routes.py` — the three endpoints. `runner.py` — background orchestrator launch (the
  seam tests stub). `cli.py` — the Click CLI. `main.py` — the FastAPI app.
