# Task 10 — OTel tracing wiring

## Context

Every LLM call, tool call, and service hop needs to be traceable to a task ID. Without this, debugging why a task took 3 minutes and cost $2 is guesswork. Phase 0 target: submit a task, see a full trace in Jaeger with spans for each agent, verifier call, sandbox exec, and context provider retrieval.

## Prereqs

- Task 03 (orchestrator).
- Task 04 (planner) and Task 05 (verifier) — for real spans to trace.

## Scope

Files to create in `packages/telemetry/`:

- `src/platform_telemetry/setup.py`:
  - `def configure(service_name: str) -> None` — sets up OTel tracer provider, OTLP exporter pointing at `OTEL_EXPORTER_OTLP_ENDPOINT`, resource with service.name.
  - Auto-instrumentation for FastAPI, httpx, SQLAlchemy, asyncpg via `opentelemetry.instrumentation.*`.
  - Called once at service startup.
- `src/platform_telemetry/decorators.py`:
  - `@traced(span_name: str, capture_args: bool = False)` — decorator that wraps async functions in a span. Adds `task_id` attribute if present in kwargs.
  - `def add_llm_attributes(span, model: str, prompt_version: str, input_tokens: int, output_tokens: int, cost_usd: float)` — helper for annotating LLM call spans.
- `src/platform_telemetry/context.py`:
  - `def set_task_context(task_id: UUID) -> None` / `def get_task_context() -> UUID | None` using contextvars.
  - Ensures nested spans get the task_id automatically.

Update each service's `main.py` to call `configure(service_name=...)` at startup.

Instrument the following span points:

- Orchestrator: one span per phase (`plan`, `build`, `verify`, `ship`).
- Planner: one span for `plan()`, with LLM attributes (model, tokens, cost).
- Developer: one span per ReAct iteration; nested spans per tool call.
- Verifier: one span per `verify()`, nested spans per runner (build/typecheck/tests/lint).
- Context Provider: one span per `retrieve()`, nested spans per MCP call.
- Sandbox: one span per `spawn` / `exec` / `destroy`.

Update `docker-compose.yml` to include Jaeger (already there from scaffold; confirm ports 16686 UI, 4317 OTLP).

Tests:

- `tests/test_setup.py` — `configure()` returns without error, tracer emits spans (use `InMemorySpanExporter`).
- `tests/test_decorators.py` — `@traced` wraps functions, propagates task_id from context, records exceptions.

## Success criteria

```bash
cd packages/telemetry
pytest -q                              # exit 0

# End-to-end: submit a task, view the trace.
make up
# All services running (orchestrator, verifier, sandbox, context-provider, task-api).
platform-cli submit --repo demo-lib --title "test" --description "..."
# Wait for completion, then:
open http://localhost:16686
# Search for service "orchestrator", find the trace for the task.
# Verify: root span for the task, children for each phase, grandchildren for
# each agent iteration and verifier call. Each LLM span has model / tokens /
# cost attributes.
```

## Non-goals

- **No cost dashboards.** Grafana / Tempo setup with cost queries is Phase 3.
- **No Langfuse integration.** Phase 1, alongside the Context Budget Manager (prompt-specific observability).
- **No sampling.** 100% traces in Phase 0. Sampling is a Phase 3 tuning concern.
- **No log correlation.** structlog logs also carry `task_id` (see CLAUDE.md); but joining traces to logs via `trace_id` is Phase 2.
- **No metrics (Prometheus).** Traces only. Metrics are Phase 3.
- **No alerts.** Phase 3.

## Effort

~3 hours (setup is quick; getting every span attributed correctly takes iterations).

## Notes

- **`configure` returns the provider and is offline-safe.** With no
  `OTEL_EXPORTER_OTLP_ENDPOINT` it installs a provider with *no* exporter — spans are
  created and dropped, nothing reaches for a collector, nothing is logged. So every
  `@traced`/instrumented path is safe in `make test`/CI with zero config. `configure` also
  takes `exporter`/`set_global`/`instrument` so tests build a provider, emit, and assert
  without fighting OTel's set-once `set_tracer_provider`.
- **Startup via FastAPI lifespan, not import.** `lifespan_for(name)` runs `configure` +
  app instrumentation on server startup. A bare `TestClient(app)` (how the service unit
  tests construct their client) never triggers lifespan, so instrumentation stays out of
  unit tests. The orchestrator (not a server) configures in `orchestrator.main.run` — the
  process entry — *not* in `Orchestrator.execute`, so a unit test driving the graph
  directly doesn't mutate global tracing state. (Found the hard way: configuring in
  `execute` set the global provider before the telemetry tests could install their
  in-memory one, and their assertions went blank.)
- **`task_id` via contextvar.** `execute` calls `set_task_context(task_id)` once; every
  nested span (`@traced` phases, planner, developer iterations, and the cross-service
  spans reached in-process) picks it up. `@traced` also honors an explicit `task_id`
  kwarg, and binds the signature so positional args (`retrieve(query, repo, mode)`) get
  captured under `capture_args` just like keyword ones.
- **asyncp​g → psycopg deviation.** The card lists asyncpg auto-instrumentation, but the
  DB layer uses psycopg (`platform_db.session`). SQLAlchemy instrumentation covers DB
  spans at the engine level instead; asyncpg instrumentation is omitted.
- **Span points instrumented:** orchestrator `run` + phase spans; planner `plan` (+ LLM
  attrs); developer `iteration` + per-`tool.<name>` (+ LLM attrs); verifier `verify` +
  per-runner (`build`/`typecheck`/`test`/`lint`); context-provider `retrieve` + per-MCP
  call (`mcp.crg.call`/`mcp.graphify.call`); sandbox `spawn`/`exec`/`destroy`.
- **Cross-service trace continuity** rides on httpx auto-instrumentation propagating trace
  context on the outbound calls (orchestrator→verifier, developer→sandbox/verifier/
  context-provider), so a task's spans stitch into one trace across processes. `task_id`
  as a span *attribute* only appears where the contextvar is set (the orchestrator
  process); downstream services get the trace linkage but not the attribute in Phase 0.
- **`docker-compose.yml`:** confirmed Jaeger (16686 UI / 4317 OTLP) and set
  `COLLECTOR_OTLP_ENABLED=true` explicitly so a pinned image still receives spans.
- **Not run end-to-end.** The in-memory-exporter tests prove span creation, nesting,
  task_id propagation, LLM attrs, and exception recording; a real Jaeger trace from a live
  submit still needs the full stack + Docker (same gate as cards 08/11).
