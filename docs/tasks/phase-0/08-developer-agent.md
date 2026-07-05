# Task 08 — Developer agent v0 (ReAct loop)

## Context

The Developer agent is a ReAct loop with tool use. Given a plan from the Planner, it reads context, edits files inside the sandbox, runs the Verifier, and iterates until verifier passes or budget cap. This is the highest-value card in Phase 0 — everything before it exists to make this loop possible.

Read ADR-0006 (Verifier is the gate) before starting.

## Prereqs

- Task 05 (Verifier).
- Task 06 (Docker sandbox).
- Task 07 (Context Provider).

## Scope

Files to create in `agents/developer/`:

- `src/developer/tools.py` — tool implementations wrapping the three services:
  - `async def retrieve(query: str, mode: str) -> str` → calls Context Provider.
  - `async def read_file(path: str, sandbox: SandboxHandle) -> str` → sandbox `cat`. (The one exception to non-negotiable #2 — reading a specific known file after retrieval is fine; searching for files is not.)
  - `async def edit_file(path: str, content: str, sandbox: SandboxHandle) -> None` → sandbox writes file.
  - `async def run_verifier(sandbox: SandboxHandle) -> VerifierResult` → calls Verifier service against the sandbox worktree.
- `src/developer/agent.py`:
  - `class DeveloperAgent(DeveloperProtocol)`:
    - `async def build(self, plan: Plan, sandbox: SandboxHandle) -> BuildResult`:
      - ReAct loop, up to N iterations (env-configured, default 15):
        - Prompt the model with plan + current state + Verifier facts (if any yet) + available tools.
        - Model picks a tool; execute it.
        - After each `edit_file`, run Verifier. If it passes, exit loop.
        - After each iteration, persist an `agent_turn` row.
      - Budget cap: `MAX_DEVELOPER_TOKENS_PER_TASK` from env. On breach, exit with `budget_exceeded`.
      - Stuck-loop detection: same tool + same args three times in a row → exit with `stuck`.
- `src/developer/models.py`:
  - `class BuildResult(BaseModel): status: Literal["passed", "budget_exceeded", "stuck", "max_iterations"]; diff: str; verifier_facts: VerifierResult`
- `tests/test_agent.py`:
  - With mocked LLM + fake sandbox + fake verifier:
    - Simulate a two-iteration path (retrieve → edit → verify pass). Agent exits `passed`.
    - Simulate a loop with same tool call three times. Agent exits `stuck`.
    - Simulate exceeding token budget. Agent exits `budget_exceeded`.
    - Each iteration writes an `agent_turn` row.
- `tests/test_agent_integration.py`:
  - Real LLM, real Context Provider (against demo-lib), real Docker sandbox, real Verifier.
  - Simple task: "add a function `sum(a: number, b: number): number` in `src/math.ts` and a test." Agent completes end-to-end with `status="passed"`.
  - Marked `@pytest.mark.integration`. Long test — set `timeout=300s`.

Update `services/orchestrator/src/orchestrator/graph.py` build node to invoke real `DeveloperAgent` (replaces fake from task 03).

## Success criteria

```bash
cd agents/developer
pytest -q                              # exit 0
ANTHROPIC_API_KEY=... pytest -q -m integration --timeout=300
# exit 0 — real task completes end-to-end.
```

End-to-end from orchestrator: submitting a task now runs the real developer. Postgres has:
- One `task_session`.
- Multiple `agent_turn` rows for the developer (one per ReAct iteration), each with real tokens/cost.
- A `verifier_run` row for each verifier call.

## Non-goals

- **No supervisor pattern.** Straight ReAct loop; the supervisor lands in Phase 2 per ADR-0005.
- **No context compression.** Full history in the prompt every iteration. Budget cap catches runaway costs. Compression is Phase 1.
- **No multiple concurrent developers.** One at a time per task.
- **No merge coordinator integration.** Diff comes back as a string; PR opening is fake (from task 03's ship node).
- **No security scanning during the loop.** Verifier calls are build/test/typecheck/lint only.
- **No LSP-based reference queries.** Retrieval is CRG/Graphify only in Phase 0.
- **No prompt caching.** Anthropic prompt caching in Phase 1 with the Context Budget Manager.

## Effort

~4 hours (real work; the ReAct loop is small but the integration test debugging is where the time goes).

## Notes

_(fill in as you go — especially any observations about the LLM's tool-use patterns and where prompts need tightening)_
