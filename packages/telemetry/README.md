# platform-telemetry

OTel tracing shared by all services and agents (card 10). Every task run becomes one
trace: a root `orchestrator.run` span with children per phase, per agent iteration, per
verifier/sandbox/retrieval call. LLM spans carry model / tokens / cost.

## Public surface

- `configure(service_name)` — build + install the tracer provider at startup. OTLP
  exporter when `OTEL_EXPORTER_OTLP_ENDPOINT` is set; **offline-safe** (no exporter, no
  errors) when it isn't, so `make test`/CI never need a collector.
- `lifespan_for(service_name)` — a FastAPI `lifespan` that configures + instruments the
  app on server startup (not import, so unit tests with a bare `TestClient` don't trigger it).
- `traced(span_name, capture_args=False)` — wrap an async function in a span; stamps
  `task_id` (from a kwarg or the contextvar), records+re-raises exceptions.
- `add_llm_attributes(span, ...)` / `current_span()` — annotate a span with LLM facts.
- `set_task_context(task_id)` / `get_task_context()` — task-scoped contextvar so nested
  spans inherit `task_id` without threading it through signatures.

## Viewing traces

`make up` brings up Jaeger (UI at http://localhost:16686, OTLP on 4317). Set
`OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317`, run the services, submit a task, and
search service `orchestrator` for the trace.

Auto-instrumentation covers FastAPI, httpx, and SQLAlchemy. (The card lists asyncpg, but
this platform uses **psycopg** — SQLAlchemy instrumentation covers DB spans at the engine
level instead.)
