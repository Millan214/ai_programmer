# Phase 0 task queue

Eleven cards, ordered. Complete in sequence — later cards assume earlier ones.

| # | Card | Effort | Depends on |
|---|---|---|---|
| 01 | Postgres schema + Alembic migrations | ~2h | scaffold |
| 02 | Versioned prompt registry package | ~2h | scaffold |
| 03 | LangGraph orchestrator skeleton | ~3h | 01, 02 |
| 04 | Planner agent v0 | ~2h | 02, 03 |
| 05 | Verifier service v0 | ~3h | scaffold |
| 06 | Docker sandbox v0 | ~4h | scaffold |
| 07 | Context Provider v0 (Graphify + CRG) | ~4h | scaffold + Graphify/CRG in target |
| 08 | Developer agent v0 (ReAct loop) | ~4h | 05, 06, 07 |
| 09 | Task submission CLI + API | ~2h | 03 |
| 10 | OTel tracing wiring | ~3h | 03, 04, 05 |
| 11 | End-to-end smoke test | ~3h | 01–10 |

**Total:** ~32h of focused work. Phase 0 timebox is 6 weeks; the remaining time absorbs debugging, target-repo prep, and the surprises that always show up.

### Follow-up cards (spawned mid-Phase-0)

Not part of the original ordered eleven; discovered while working a card and split out rather than smuggled into scope.

| # | Card | Effort | Depends on | Spawned by |
|---|---|---|---|---|
| 12 | Postgres-backed LangGraph checkpointer | ~3h | 01, 03 | 03 |

## Card conventions

Each card has:

- **Title** — one line, imperative.
- **Context** — one paragraph, why this exists.
- **Prereqs** — cards or setup required first.
- **Scope** — files and paths to create or edit. Exhaustive.
- **Success criteria** — commands. If they don't exit 0, the card isn't done.
- **Non-goals** — what to explicitly not build. Keeps scope creep in check.
- **Effort** — rough hours.
- **Notes** — surprises, decisions, questions. Fill this in as you work.

## Working the queue

- **One card per Claude Code task.** Do not batch.
- **Read the referenced ADRs before starting.** They contain constraints not repeated in the card.
- **Update `## Notes` before closing a card.** Anything you learned that changes a later card or an ADR.
- **When a card discovers new work, spawn a follow-up card.** Do not sneak scope into an existing card.
- **Commit at every green success criterion.** Small commits, clear messages.

## Definition of done for Phase 0

`docs/tasks/phase-0/11-smoke-test.md` passes: the platform takes a well-scoped task ("add a `hasPermission(user, action)` helper with tests"), produces a passing PR against the demo repo, and the entire run is auditable in Postgres. That's the exit criterion. Everything else in Phase 0 is means, not end.
