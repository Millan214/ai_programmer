# ADR-0005: Supervisor + inner loop over rigid FSM

## Status

Accepted, 2026-07. Phase 0 uses a thin outer FSM only; supervisor lands in Phase 2.

## Context

The original blueprint proposed a strict linear FSM: `PLANNING → ARCHITECTURE → IMPLEMENTATION → REVIEW → SECURITY → QA → DOCUMENTATION → HUMAN APPROVAL → CREATE PR → COMPLETE`, with a single back-edge (`REVIEW fail → IMPLEMENTATION`).

Real software work doesn't fit that shape. Implementing exposes bad design assumptions (need to bounce to Architecture). QA finds gaps the Architect should have caught. Security review triggers a redesign. A single back-edge forces either wasteful ping-pong through phases that aren't the problem, or bad answers pushed through because the FSM won't let the process backtrack cleanly.

Two things go wrong with a strict FSM here:

1. **The FSM encodes assumptions about which back-edges matter.** These assumptions turn out to be wrong under real workloads, and changing them means rewriting the graph.
2. **The FSM doesn't know when it's stuck.** A rigid state machine cycles between phases; a smarter driver can detect a stuck loop and escalate.

## Decision

**Two-level workflow model:**

- **Outer FSM (thin)** — four phases: `Plan → Build → Verify → Ship`. Mostly moves forward; back-edges permitted under explicit, named conditions (e.g. Verify → Plan when Verifier reports architectural mismatch).
- **Inner loop (during Build)** — driven by a **supervisor agent** whose only job is to look at task state and decide the next action. The supervisor's decisions include: read files, call verifier, ask reviewer, ask architect (redesign), ask human, mark done.

The supervisor is itself an LLM agent with a tight prompt, seeing summarized state (not the full history). Its decisions are persisted as `agent_turn` rows and are auditable events.

Supervisor loop pseudocode:

```
loop:
  state = read_state()
  next = supervisor.decide(state, policies, budget)
  match next:
    read_files(...)     → Context Provider
    edit_files(...)     → Developer agent in sandbox
    run_verifier(...)   → Verifier subsystem
    ask_reviewer(...)   → Reviewer agent
    ask_architect(...)  → Architect agent (redesign)
    ask_human(...)      → HITL queue
    done()              → exit loop
  persist_event(next, result)
  if budget_exceeded or supervisor.stuck: escalate
```

Phase 0 skips the supervisor — the Build node runs a straight ReAct loop in the Developer agent. Supervisor lands in Phase 2 when the agent roster grows enough to need choice.

## Consequences

- **Flexible.** New agents and back-edges don't require FSM surgery — they become supervisor decisions.
- **Auditable.** Each supervisor decision is a persisted event with model, prompt version, cost. Post-hoc analysis of "why did the platform do X" is a SQL query.
- **Depends on prompt quality.** A bad supervisor prompt loops the platform. Mitigated by budget caps (circuit-breaker at token/cost limits), stuck-loop detection (same action N times → escalate), and prompt regression tests.
- **Harder to reason about statically.** A rigid FSM's behavior is visible from the graph; a supervisor's behavior emerges from prompt + state. Traces become the source of truth for behavior; observability discipline is non-negotiable.
- **Testing shifts.** Instead of "does the FSM traverse phases correctly", tests become "given state X, does the supervisor pick action Y" — closer to prompt evaluation than to workflow testing.

## Alternatives considered

- **Strict FSM with many predefined back-edges.** Marginally more flexible than the original blueprint. Rejected because we can't predict all the back-edges we'll need, and every new agent adds combinatorial complexity to the FSM.
- **Pure autonomous loop, no phases.** A single supervisor drives everything from task submission to PR. Simplest model, hardest to reason about, most vulnerable to prompt drift. Rejected in favor of the hybrid — outer phases give humans and observability tooling a natural axis.
- **Behavior trees.** Explicit tree of tactics with fallbacks. Well-suited to game AI; poorly-suited to LLM-driven code work where the space of tactics is open-ended.

## References

- Strategy doc §3.1 (supervisor pattern), §5 (revised workflow model)
- Related ADRs: ADR-0001 (LangGraph hosts both outer FSM and inner supervisor), ADR-0006 (Verifier facts drive supervisor decisions)
