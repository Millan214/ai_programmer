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

_(fill in as you go)_
