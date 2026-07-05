# Task 03 — LangGraph orchestrator skeleton

## Context

The orchestrator is the outer FSM: `Plan → Build → Verify → Ship`. In Phase 0 it wires together stub nodes and persists state to Postgres. Real agent calls come in tasks 04 and 08; real verifier in 05. This card gets the skeleton running end-to-end with fakes.

Read ADR-0001 and ADR-0005 before starting.

## Prereqs

- Task 01 (Postgres schema) complete.
- Task 02 (prompt registry) complete.

## Scope

Files to create in `services/orchestrator/`:

- `src/orchestrator/state.py` — `TaskState` TypedDict / Pydantic model with fields: `task_id`, `phase`, `plan`, `edits`, `verifier_facts`, `budget_remaining`.
- `src/orchestrator/graph.py` — LangGraph `StateGraph` with four nodes:
  - `plan_node` — calls a `PlannerProtocol` (Protocol/ABC). Phase 0 impl is a fake that returns a stub plan. Real one lands in task 04.
  - `build_node` — calls a `DeveloperProtocol`. Phase 0 impl is a fake that returns stub edits. Real one lands in task 08.
  - `verify_node` — calls a `VerifierProtocol`. Phase 0 impl is a fake that returns `{"build": "pass", "tests": "pass"}`. Real one lands in task 05.
  - `ship_node` — persists a fake PR URL to the task row, marks status `completed`.
- `src/orchestrator/persistence.py` — LangGraph checkpointer backed by `packages/db`. On every node transition, upserts `task_session` and writes an `agent_turn` row (with placeholder token/cost fields for now).
- `src/orchestrator/protocols.py` — `PlannerProtocol`, `DeveloperProtocol`, `VerifierProtocol` interfaces.
- `src/orchestrator/main.py` — `async def run(task_id: UUID) -> None` — loads the task, invokes the graph, updates status.
- `tests/test_graph.py`:
  - With all fakes wired, invoking `run(task_id)` for a fresh task transitions through all four phases and ends in `completed`.
  - Task session and per-node `agent_turn` rows are persisted.
  - A failed verify (fake returns failure) does not proceed to ship; task ends in `failed_verify` status.

## Success criteria

```bash
cd services/orchestrator
pytest -q                              # exit 0
pytest -q -m integration               # exit 0 (with make up running)
```

Manually: submit a task via a Python REPL:

```python
from orchestrator.main import run
from platform_db.repositories.tasks import create
import asyncio
task_id = asyncio.run(create(repo="demo-lib", title="test", description="stub"))
asyncio.run(run(task_id))
```

Postgres shows the task in `completed` status, with one `task_session` and four `agent_turn` rows.

## Non-goals

- **No supervisor pattern.** Build node runs its (fake) developer once and moves on. Supervisor lands in Phase 2 per ADR-0005.
- **No real LLM calls.** All agent protocols have fake implementations for this card.
- **No back-edges.** Phase 0 outer FSM is strictly forward; verify-fail terminates instead of looping.
- **No real verifier.** Fake `{"build": "pass", "tests": "pass"}` is fine.
- **No PR opening.** Ship node writes a fake PR URL string. Real merge coordinator is Phase 1+.
- **No cost tracking.** Placeholder zeros in `agent_turn` cost/token fields.

## Effort

~3 hours.

## Notes

- **"LangGraph checkpointer backed by packages/db" was deferred — decision, not omission.**
  A conformant `BaseCheckpointSaver` needs a `checkpoints` table, which the card-01 schema
  doesn't define, and card 01 owns the schema (no ad-hoc tables). So Phase 0 splits the concern:
  the graph uses LangGraph's in-memory `MemorySaver` for run-local checkpointing, and
  `persistence.py` writes the *auditable* rows the ADR actually cares about (one `task_session`
  per run, one `agent_turn` per node transition). Follow-up card `12-db-checkpointer.md` spawned
  for the real Postgres-backed checkpointer (needs a schema migration → Alembic + card-01 owner).
- **Ship's "fake PR URL" is stored on the ship `agent_turn`'s `output_ref`**, because the `task`
  table has no PR/URL column in the card-01 schema (and card 01 explicitly defers `pr`/`review`
  tables). This keeps it auditable without a schema change. Design question flagged for review: if
  a first-class PR reference is wanted on `task` before Phase 1's merge coordinator, that's a
  card-01 migration.
- **Protocols exchange dicts, not Pydantic models.** `PlannerProtocol.plan -> dict[str, object]`
  etc., so the dependency arrow stays one-way (planner/developer packages → orchestrator
  protocols, never the reverse) and matches LangGraph state + JSONB storage. Card 04 says
  `PlannerAgent.plan -> Plan`; to keep satisfying the protocol, its impl should return
  `plan.model_dump()`. Noted at the top of `protocols.py`.
- **`TaskState` carries two fields beyond the card's six:** `session_id` (FK linkage for every
  `agent_turn`) and `task_description` (the Planner's input). Both are mechanical plumbing, not new
  domain state.
- **Tightened card-01's db types as a side effect:** the repositories/models used bare `dict`,
  which reads as `dict[Unknown, Unknown]` and fails pyright strict the moment strict code
  (services) imports them. Changed to `dict[str, object]` across `models.py` and the repositories.
  Also added `py.typed` markers to `platform_db`, `orchestrator`, and `prompts` — without them,
  strict-mode imports of our own packages raise `reportMissingTypeStubs`. These are prerequisites
  every future service/agent card would otherwise re-hit; done once here.
- **Two pyright rules are disabled for `graph.py` only** (`reportMissingTypeStubs`,
  `reportUnknownMemberType`), documented inline: LangGraph 1.2 ships no stubs for `langgraph.graph`
  and types `add_node`/`compile` with partially-unknown generics. The file is pure LangGraph glue
  covered by `test_graph.py`; our own logic keeps full strict typing.
- **Windows:** same psycopg selector-loop gotcha as card 01; `tests/conftest.py` sets the
  `SelectorEventLoop` factory. See [[card-01]] notes.
