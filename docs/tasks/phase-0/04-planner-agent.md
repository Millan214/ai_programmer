# Task 04 — Planner agent v0

## Context

The Planner takes a task description and produces a structured plan: subtasks, files likely affected, risks, and an estimated scope. First real LLM call in the platform. Replaces the fake `PlannerProtocol` impl from task 03.

## Prereqs

- Task 02 (prompt registry) — loads the planner prompt.
- Task 03 (orchestrator skeleton) — defines `PlannerProtocol`.

## Scope

Files to create in `agents/planner/`:

- `src/planner/agent.py`:
  - `class PlannerAgent(PlannerProtocol)` implementing the protocol from `services/orchestrator/protocols.py`.
  - `async def plan(self, task_description: str) -> Plan`
  - Uses `anthropic.AsyncAnthropic` with model from env (default `claude-opus-4-7`).
  - Loads prompt via `prompts.registry.render(PromptRef("planner", "plan", active), task_description=task_description)`.
  - Asks the model for JSON output (system prompt instructs, response parsed).
  - Records the call as an `agent_turn` row: agent="planner", model, prompt_version, tokens, cost, tool_calls=[].
- `src/planner/models.py` — Pydantic:
  - `class Plan(BaseModel): subtasks: list[Subtask]; risks: list[str]; estimated_files: list[str]`
  - `class Subtask(BaseModel): title: str; description: str; acceptance: str`
- `tests/test_planner.py`:
  - Unit test with a mocked Anthropic client: given fixed model output, `plan()` parses correctly.
  - Malformed JSON output → retries once, then raises `PlannerOutputError`.
  - `agent_turn` row is created with correct fields (assert against DB in test setup).
- `tests/test_planner_integration.py`:
  - Real Anthropic call with a small task description ("add a `hasPermission(user, action)` helper"). Marked `@pytest.mark.integration`. Skipped unless `ANTHROPIC_API_KEY` set.

Update `services/orchestrator/src/orchestrator/graph.py` to wire in the real `PlannerAgent` in place of the fake.

## Success criteria

```bash
cd agents/planner
pytest -q                              # exit 0
ANTHROPIC_API_KEY=... pytest -q -m integration  # exit 0
```

End-to-end from task 03:

```python
# Same submit-a-task flow as task 03, now with real planner.
```

- `agent_turn` for the planner row shows non-zero input/output tokens and a real cost.
- The `plan` field on `task_session` contains a valid `Plan` JSON.

## Non-goals

- **No architect agent.** Planner outputs subtasks; refining them into a design is Phase 2.
- **No plan revision loop.** One shot, no back-and-forth in Phase 0.
- **No streaming.** Non-streaming completion is fine at Phase 0.
- **No prompt caching.** Anthropic prompt caching lands in Phase 1 with the Context Budget Manager.
- **No fallback model.** Model router is Phase 2. For now, one model, from env.
- **No tool use by the planner.** It gets a task description and returns a plan. No retrieval yet.

## Effort

~2 hours.

## Notes

- **Protocol change: `PlannerProtocol.plan(description, session_id) -> PlanDict`.** The
  card 03 protocol didn't carry `session_id`; the real Planner needs it to write its
  own `agent_turn` row. `FakePlanner` gained the parameter (unused) plus an optional
  `TurnRecorder` in its ctor so the fake path still stamps a placeholder turn — the
  card 03 DB integration test keeps expecting four rows without change to its assertion.
- **Persistence split: added `advance_phase` and `record_agent_turn`.** `record_node`
  (advance-phase + placeholder-turn) is kept for build/verify/ship where fakes still
  live. `_plan_node` now uses `advance_phase` only, because the Planner writes its
  own real turn. Card 03's `test_graph.py` was updated in step: `FakePersistence`
  tracks both surfaces and its assertions cover them explicitly. See [[card-03]] for
  why this was deferrable back then and lands now.
- **`PlannerAgent.plan` returns `Plan`, not `PlanDict`.** Card 04's spec pins the
  typed return; card 03's protocol pins `PlanDict`. `PlannerProtocolAdapter` bridges
  at the graph seam so protocols stay Pydantic-free (per card 03's `protocols.py`
  docstring). `main.py` wires the adapter conditionally: real `PlannerAgent` when
  `ANTHROPIC_API_KEY` is set, `FakePlanner` (with recorder) otherwise — the graph runs
  offline in CI without the key.
- **Cost table: hardcoded per-model dictionary in `planner/pricing.py`.** Card 04's
  success criteria calls for "a real cost", but there's no model router yet (Phase 2).
  Numbers reflect published Claude 4.x tiers as of 2026-07; unknown models return
  `None` (row still persists — the schema allows a null `cost_usd`). Replace this
  when the model router lands.
- **Retry policy: exactly one, on parse failure only.** JSON decode error or Pydantic
  validation error triggers a single retry (same prompt, no rephrasing). A second
  failure raises `PlannerOutputError`. Network / API errors are *not* retried here —
  those bubble to the orchestrator, which is where a retry policy will eventually
  live once we have a supervisor (ADR-0005, Phase 2).
- **Anthropic client injection.** `PlannerAgent` accepts an optional
  `AsyncAnthropic` in its ctor; unit tests pass a `_StubClient` that scripts responses
  by pushing real `anthropic.types.Message` instances (via `model_construct`) — no
  http mocking library needed. `# type: ignore[arg-type]` on the three test-site ctor
  calls documents the intentional stubbing.
- **Model default from env, fallback `claude-opus-4-7`.** Read once at construction:
  `os.environ.get("PLANNER_MODEL") or "claude-opus-4-7"`. Kept a constant instead of
  the module-scanning path so tests can override cleanly with the `model=` kwarg.
- **`prompt_version` format on the persisted turn: `planner/plan@vN`.** More
  self-documenting than the raw version string when reading the row directly.
- **`agents/planner` now depends on `platform-orchestrator`.** Only for the
  `TurnRecorder` protocol import — no runtime coupling. Matches card 03's guardrail:
  agent packages depend on orchestrator's protocol module, never the reverse.
