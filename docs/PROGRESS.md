# Progress

Running status of the Phase 0 work queue. Update whenever a card lands or a new one spawns.
Cross-references: [phase-0 task cards](tasks/phase-0/), [ADRs](adr/), [CLAUDE.md](../CLAUDE.md).

## Phase 0 — end-to-end skeleton

**Exit criterion.** The platform takes `add a hasPermission(user, action) helper with tests`,
produces a passing PR against the demo repo, and the entire run is auditable in Postgres.
(From [11-smoke-test.md](tasks/phase-0/11-smoke-test.md).)

### Ordered cards

| # | Card | Status | Landed in | Notes |
|---|---|---|---|---|
| 01 | [Postgres schema + Alembic migrations](tasks/phase-0/01-postgres-schema.md) | Done | `53cb4b6` | `task`, `task_session`, `agent_turn`, `verifier_run` in place. |
| 02 | [Versioned prompt registry](tasks/phase-0/02-prompts-package.md) | Done | `5ebe9ca` | `prompts/versions.toml` pins active; loaders via `PromptRef`. |
| 03 | [LangGraph orchestrator skeleton](tasks/phase-0/03-orchestrator-skeleton.md) | Done | `c5560b0` | Outer FSM (Plan→Build→Verify→Ship) with fakes; MemorySaver (real Postgres checkpointer split to card 12). |
| 04 | [Planner agent v0](tasks/phase-0/04-planner-agent.md) | Done | `602ed7f` | Real Anthropic call, JSON parse w/ one retry, own `agent_turn` write via injected `TurnRecorder`. |
| 05 | [Verifier service v0](tasks/phase-0/05-verifier-service.md) | Done | `5cea0a6` | Runs build/test/typecheck/lint. **Does not yet write `verifier_run`** — see review finding R2. |
| 06 | [Docker sandbox v0](tasks/phase-0/06-sandbox-docker.md) | Done | `9255da3` | Phase 0 container runner; Firecracker deferred (ADR-0003). |
| 07 | [Context Provider v0 (Graphify + CRG)](tasks/phase-0/07-context-provider.md) | Done | `a2abdb1` | Sole retrieval gateway (ADR-0002). |
| 08 | [Developer agent v0 (ReAct loop)](tasks/phase-0/08-developer-agent.md) | Done | *working tree* | ReAct loop w/ tool use, per-iteration `agent_turn`, budget/stuck/iteration caps. Integration test env-gated — needs a demo repo in `target-repos/` (see card Notes). |
| 09 | [Task submission CLI + API](tasks/phase-0/09-task-cli.md) | Not started | — | `task-api` HTTP + CLI wrapper. |
| 10 | [OTel tracing wiring](tasks/phase-0/10-otel-tracing.md) | Not started | — | Jaeger locally; spans across services. |
| 11 | [End-to-end smoke test](tasks/phase-0/11-smoke-test.md) | Not started | — | The exit criterion above. |

### Follow-up cards (spawned mid-Phase-0)

| # | Card | Status | Spawned by | Notes |
|---|---|---|---|---|
| 12 | [Postgres-backed LangGraph checkpointer](tasks/phase-0/12-db-checkpointer.md) | Not started | 03 | Needs a `checkpoints` migration owned by card 01's schema surface. |

### Progress so far

- **8 of 11 ordered cards landed** (01–08).
- **The platform can now write code**: card 08's DeveloperAgent runs a real ReAct loop
  (Claude Sonnet by default, `DEVELOPER_MODEL` to override) — retrieve via Context
  Provider, read/edit through the sandbox, verifier auto-run after every edit, exits
  only on a green verifier run / budget cap / stuck detection / iteration cap. One
  `agent_turn` row per iteration with real tokens and cost. The pricing table moved to
  `platform_shared.pricing` so both agents share it.
- **First real LLM call is live** as of card 04: PlannerAgent → Anthropic → parsed `Plan` →
  persisted `agent_turn` with real tokens and computed cost. The graph still falls back to
  `FakePlanner` when `ANTHROPIC_API_KEY` is absent so `make test` stays offline.
- **Verifier/Reviewer split (ADR-0006) is honoured so far**: no agent claims a fact the
  Verifier hasn't confirmed — but the Verifier is a fake until card 05.
- **1 follow-up card spawned** (12, the Postgres checkpointer) — split out because it
  needs a schema migration and card 01 owns the schema surface.

### Next up

Card 09 (task submission CLI + API). The two prior blockers are cleared: R2 (verifier_run
persistence) is fixed, and `target-repos/demo-lib` now exists — a tiny TS library
(`multiply`, `capitalize`) on the same pinned toolchain as the verifier fixture, verified
green (build/typecheck/3 tests/lint). Run `make demo-repo` once per machine to git-init it
and install its toolchain, then set `DEMO_REPO_PATH` to run card 08's integration test.

## Code review — 2026-07-05 (cards 01–07)

Full-codebase review after card 07 landed. Baseline was green (ruff clean, pyright strict
0 errors, 52 unit tests passing). Findings below, prioritized. None are fixed yet.

### Violations of CLAUDE.md core principles

- **R1 — Planner retry drops an LLM call from the audit trail**
  (`agents/planner/src/planner/agent.py:55-65`). On the malformed-JSON retry path two API
  calls are made but only the second response is persisted as an `agent_turn`. Breaks
  principle 4 ("every LLM call is a persisted event"). Fix: record a turn per response.
- **R2 — Verifier facts are never persisted.** ✅ **Fixed.** `POST /verify` now takes an
  optional `session_id` and writes a `verifier_run` row (build/typecheck/tests/lint JSONB)
  before returning. Done in the service so every caller inherits it: the orchestrator's
  Verify node and the Developer's in-loop runs both thread `session_id` through. Callers
  without a session (ad-hoc verification) still get facts, no row.
- **R3 — Ship gate ignores typecheck and lint**
  (`services/orchestrator/src/orchestrator/graph.py:32-34`). `_verify_passed` checks only
  `build` and `tests`; the real Verifier returns `typecheck`/`lint` too, so a change with
  type errors ships. Either gate on all four or document the Phase 0 scope decision.
- **R4 — No structured logging anywhere.** CLAUDE.md mandates structlog JSON with
  `task_id`; no service or agent emits a single log line.

### Correctness / robustness

- **R5 — Failure paths leave task status dangling**
  (`orchestrator/graph.py:100-119`). A raising planner or verifier exits `execute` via
  exception and the task never reaches a terminal status; `task_session.ended_at` is never
  set by any code path. Wrap `ainvoke`, record a failed status, set `ended_at`.
- **R6 — Planner doesn't detect `max_tokens` truncation.** A truncated response fails
  parsing and triggers a retry that will hit the same 2000-token cap. Check
  `stop_reason == "max_tokens"`; also strip markdown code fences before JSON parse.
- **R7 — Sandbox exec timeout leaves inconsistent state**
  (`services/sandbox/src/sandbox/controller.py:84-95`). On timeout: container killed but
  not removed, worktree left on disk, handle still registered, `docker exec` client
  process not reaped. Timeout path should run full `destroy`.
- **R8 — Git is broken inside the sandbox container.** A linked worktree's `.git` file
  points at the main repo's absolute host path; only the worktree is mounted, so git
  fails inside the container. Blocks card 08's developer agent using git in-sandbox.
- **R9 — No verifier subprocess timeouts** (`verifier/runners/pnpm.py`). A hung pnpm run
  hangs `POST /verify` forever. Mirror the sandbox's `wait_for` + kill.
- **R10 — The four verifier runners race on one worktree**
  (`verifier/service.py:24-29`). build/typecheck/test/lint run concurrently in the same
  cwd (dist/ writes during tests, tsbuildinfo contention). Run sequentially or document
  why the demo repo is safe.
- **R11 — Windows fragility.** `" ".join(cmd)` into `create_subprocess_shell` with no
  quoting (`pnpm.py:54-60`; use `subprocess.list2cmdline`), and
  `SANDBOX_ROOT = Path("/tmp/sandbox")` (`controller.py:15`) resolves to
  `<drive>\tmp\sandbox` on Windows hosts.
- **R12 — No container hardening.** `docker run` without `--network none`, memory/CPU/pids
  limits, runs as root. Cheap to tighten now.

### Smaller cleanups

- **R13** — Inconsistent HTTP-boundary error handling: Context Provider lets
  `GraphifyClientError`/`CRGClientError` escape as raw 500s; sandbox DELETE is the one
  endpoint not catching `SandboxError` and skips handle removal on failure.
- **R14** — Missing FK indexes (`agent_turn.session_id`, `task_session.task_id`,
  `verifier_run.session_id`); statuses/phases are free-form strings with no
  CHECK/Literal.
- **R15** — Per-call `httpx.AsyncClient` in Graphify/CRG clients and
  `VerifierHttpClient`; hold one client per instance or use FastAPI lifespan.
- **R16** — `build_graph()` recompiles per `execute()`; `registry.active_version`
  re-reads `versions.toml` every call.
- **R17** — Evidence loss on failure: `parse_vitest_json` fallback returns bare `fail`
  with no output tail; typecheck fail with zero parsed errors discards raw output.
- **R18** — `exec` shadows the builtin in the sandbox module.

Suggested order: R1–R3 and R5 first (small fixes, principle-level), then R7–R9 before
card 08, the rest opportunistically.

## Higher phases (context, not tracked here)

- **Phase 1** — real merge coordinator, Langfuse for prompt views, Firecracker sandboxes.
- **Phase 2** — supervisor + inner loop over rigid FSM (ADR-0005), OPA policy (ADR-0004),
  Reviewer agent, Architect, model router.
- **Phase 3+** — auth, quotas, multi-tenant; Temporal candidate to replace LangGraph.
