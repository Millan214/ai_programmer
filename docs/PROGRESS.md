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
| 04 | [Planner agent v0](tasks/phase-0/04-planner-agent.md) | Done | *pending squash commit* | Real Anthropic call, JSON parse w/ one retry, own `agent_turn` write via injected `TurnRecorder`. |
| 05 | [Verifier service v0](tasks/phase-0/05-verifier-service.md) | Not started | — | Runs build/test/typecheck/lint; writes `verifier_run`. |
| 06 | [Docker sandbox v0](tasks/phase-0/06-sandbox-docker.md) | Not started | — | Phase 0 container runner; Firecracker deferred (ADR-0003). |
| 07 | [Context Provider v0 (Graphify + CRG)](tasks/phase-0/07-context-provider.md) | Not started | — | Sole retrieval gateway (ADR-0002). |
| 08 | [Developer agent v0 (ReAct loop)](tasks/phase-0/08-developer-agent.md) | Not started | — | Reads via CP, edits in sandbox. |
| 09 | [Task submission CLI + API](tasks/phase-0/09-task-cli.md) | Not started | — | `task-api` HTTP + CLI wrapper. |
| 10 | [OTel tracing wiring](tasks/phase-0/10-otel-tracing.md) | Not started | — | Jaeger locally; spans across services. |
| 11 | [End-to-end smoke test](tasks/phase-0/11-smoke-test.md) | Not started | — | The exit criterion above. |

### Follow-up cards (spawned mid-Phase-0)

| # | Card | Status | Spawned by | Notes |
|---|---|---|---|---|
| 12 | [Postgres-backed LangGraph checkpointer](tasks/phase-0/12-db-checkpointer.md) | Not started | 03 | Needs a `checkpoints` migration owned by card 01's schema surface. |

### Progress so far

- **4 of 11 ordered cards landed** (01–04). ~10h of the ~32h Phase 0 estimate.
- **First real LLM call is live** as of card 04: PlannerAgent → Anthropic → parsed `Plan` →
  persisted `agent_turn` with real tokens and computed cost. The graph still falls back to
  `FakePlanner` when `ANTHROPIC_API_KEY` is absent so `make test` stays offline.
- **Verifier/Reviewer split (ADR-0006) is honoured so far**: no agent claims a fact the
  Verifier hasn't confirmed — but the Verifier is a fake until card 05.
- **1 follow-up card spawned** (12, the Postgres checkpointer) — split out because it
  needs a schema migration and card 01 owns the schema surface.

### Next up

Card 05 (Verifier service v0). Prereq is only the scaffold — no blockers.

## Higher phases (context, not tracked here)

- **Phase 1** — real merge coordinator, Langfuse for prompt views, Firecracker sandboxes.
- **Phase 2** — supervisor + inner loop over rigid FSM (ADR-0005), OPA policy (ADR-0004),
  Reviewer agent, Architect, model router.
- **Phase 3+** — auth, quotas, multi-tenant; Temporal candidate to replace LangGraph.
