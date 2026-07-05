# CLAUDE.md

Standing context for Claude Code sessions in this repo. Read this before any task.

## What this is

An AI Coding Platform: a multi-agent system that plans, implements, reviews, tests, documents, and ships software changes as pull requests. Agents run inside a LangGraph orchestrator, share retrieval through a single Context Provider, execute code inside sandboxes, and have their work checked by a factual Verifier before an LLM Reviewer sees it.

We're currently in **Phase 0**. Goal: end-to-end skeleton that completes a trivial task on one demo target repo. See `docs/tasks/phase-0/` for the work queue.

## Tech stack

- **Python 3.12** for all platform services and agents. uv workspaces at the root.
- **TypeScript** for the operator console only (`apps/console/`). pnpm workspaces.
- **LangGraph** as orchestrator. See ADR-0001. Temporal is a candidate for Phase 3+.
- **Postgres 16** for all structured state. SQLAlchemy models in `packages/db/`, Alembic migrations.
- **Graphify + `code-review-graph` (CRG)** as the code-intelligence layer. See ADR-0002. Both installed per-target-repo via `uv tool install`, results committed alongside the code.
- **Docker** for Phase 0 sandboxing. Firecracker in Phase 1. See ADR-0003.
- **OPA** for policy enforcement, starting Phase 2. See ADR-0004.
- **OTel** for tracing everywhere. Jaeger locally, Tempo in production. Langfuse for prompt-specific views (Phase 1+).
- **FastAPI** for HTTP services. **Ruff** for lint. **Pyright** strict for `services/` and `agents/`.
- **Biome** for TypeScript. **Next.js 15** app-router for the console.

## Repo layout

```
prompts/            # versioned prompt registry, imported by agents
services/
  orchestrator/     # LangGraph state graph, outer FSM
  context-provider/ # single retrieval gateway (Graphify + CRG + more)
  verifier/         # runs build/test/typecheck/lint/scanners
  sandbox/          # spawns sandboxed exec environments
  task-api/         # HTTP submission + CLI
agents/
  planner/          # task decomposition
  developer/        # ReAct loop, edits code
  (reviewer, security, qa, docs — Phase 2+)
packages/
  db/               # SQLAlchemy models, Alembic
  telemetry/        # OTel setup
  shared/           # cross-cutting utils
apps/
  console/          # Next.js operator UI
target-repos/       # demo repo(s) the platform operates on
docs/
  adr/              # architectural decisions
  tasks/phase-0/    # current work queue
```

## Core principles (non-negotiable)

1. **Verifier reports facts. Reviewer interprets.** No agent claims a factual thing (tests pass, types clean, build green) that the Verifier hasn't confirmed. See ADR-0006.
2. **Context Provider is the only retrieval path.** No agent reads files directly. This is where budgets, caching, and retrieval fusion happen. See ADR-0002.
3. **Prompts are versioned files.** Every prompt lives in `prompts/src/prompts/versions/`, is loaded via the registry, and the version served is recorded on every `agent_turn`. Do not inline prompts in agent code.
4. **Every LLM call is a persisted event.** `agent_turn` in Postgres records model, prompt version, input/output tokens, cost, tool calls. If you're calling an LLM without persisting, you're doing it wrong.
5. **Supervisor pattern for iterative work.** The outer FSM (Plan/Build/Verify/Ship) is thin. Loops and back-edges live in a supervisor's decisions, which are themselves persisted events. See ADR-0005.
6. **No secrets in sandboxes.** Sandbox containers get code, not credentials. The Verifier and sandbox controller are the only components that see repo secrets, and only when the policy engine allows it.

## Python conventions

- **Type everything.** Pyright strict for services and agents. `Any` is a code smell; use `object` or a proper union.
- **Async by default** in services. Use `async def` for anything hitting the DB, HTTP, or a subprocess. `httpx.AsyncClient`, not `requests`.
- **No global state.** Dependency injection via FastAPI's `Depends`, or explicit factory functions for non-web contexts.
- **Errors as exceptions, not tuples.** Domain-specific exception classes in each service (`OrchestratorError`, `VerifierTimeoutError`), caught at the HTTP boundary.
- **Structured logging.** `structlog` with JSON output. Every log line has a `task_id` field when in a task context.
- **Tests colocated in `tests/` at each package root.** Fixtures shared via `conftest.py`. Integration tests marked `@pytest.mark.integration` and skipped by default; unit tests run on every `make test`.
- **Lines ≤ 100 chars.** Ruff enforced.

## TypeScript conventions

- Only the console app for now. Keep it minimal until Phase 2.
- App router, server components by default.
- No global state libraries yet. Server data via React Server Components, client state via `useState`. Zustand goes in when it earns its place.

## How to add an agent

1. Create `agents/<name>/` with `pyproject.toml` (workspace member), `src/<name>/agent.py`, `tests/`.
2. Register the agent in `services/orchestrator/src/orchestrator/agents.py`.
3. Add prompt versions in `prompts/src/prompts/versions/<name>/`.
4. Add a smoke test that mocks the LLM and asserts the agent's tool-call surface.
5. Update `docs/adr/` if this changes any load-bearing decision.

## How to add a prompt version

1. Add file: `prompts/src/prompts/versions/<agent>/<name>@v<N>.md`. Never edit an existing version file; bump the version.
2. Update the registry entry in `prompts/src/prompts/registry.py`.
3. Add or update tests in `prompts/tests/` that pin structural properties (contains section X, mentions tool Y).
4. When ready to promote, change the `active_version` in the registry. Do not delete old versions; historical `agent_turn` rows reference them.

## Testing conventions

- `make test` = unit tests only. Fast, deterministic, no network, no Docker.
- `make test-integration` = adds `@pytest.mark.integration` tests. Requires `make up`.
- `make test-e2e` = end-to-end tests, submit a task and assert PR opened. Slow, run in CI nightly.
- Coverage is measured but not gated in Phase 0. Verifier + smoke tests are the gate.

## Verifier / CI expectations

- `make check` must be green before any commit. Ruff + Pyright + Biome.
- `make test` must be green before any push.
- CI runs `make check && make test`. E2E runs separately, nightly.
- Never disable a lint or type error without a comment explaining why. `# type: ignore` requires a reason.

## What NOT to do

- **Do not read files directly from agent code.** Always go through Context Provider.
- **Do not inline prompts.** Always through the registry.
- **Do not add auth, quotas, multi-tenant fields** in Phase 0. Those land in Phase 3.
- **Do not add fields to Postgres tables** without a reviewed Alembic migration. No `create_all()` in Phase 0 either — Alembic from day one.
- **Do not skip `agent_turn` persistence** just because it's inconvenient in a test. Use the test fixture.
- **Do not run `pip install` in a service.** uv only.
- **Do not commit `.env`, `graphify-out/`, or `.code-review-graph/` in this platform repo.** They belong in target repos, not here.

## When in doubt

1. Check the relevant ADR in `docs/adr/`.
2. Check the current task card in `docs/tasks/phase-0/`.
3. Check the strategy doc in `docs/AI_Coding_Platform_Analysis_and_Plan.md` (kept for reference).
4. If none of those answer it, mark it as a design question in the task card's `## Notes` section and ask the human before deciding.

## ADR index

- ADR-0001 — LangGraph as orchestrator
- ADR-0002 — Graphify + CRG as the code-intelligence layer
- ADR-0003 — Firecracker microVMs for sandbox execution (Docker in Phase 0)
- ADR-0004 — OPA for policy enforcement
- ADR-0005 — Supervisor + inner loop over rigid FSM
- ADR-0006 — Verifier (facts) separate from Reviewer (interpretation)
