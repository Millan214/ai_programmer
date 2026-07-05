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

_(fill in as you go)_
