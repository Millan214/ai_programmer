# ADR-0001: LangGraph as orchestrator

## Status

Accepted, 2026-07. Revisit in Phase 3 if durability semantics become a bottleneck.

## Context

The platform coordinates multiple agents (Planner, Developer, Verifier initially; Reviewer, Security, QA, Docs, DevOps later) plus non-agent subsystems (Verifier, sandbox, merge coordinator). We need an orchestrator that:

- Runs an outer state machine over task phases.
- Hosts an inner supervisor loop that decides the next action based on task state.
- Persists every step so tasks are resumable after process restarts.
- Integrates naturally with LLM tool-use and Python-side retrieval, since both live in Python.
- Doesn't lock us into a specific model or vendor.

## Decision

Use **LangGraph** (Python) as the orchestrator.

- Outer FSM implemented as a LangGraph `StateGraph` with nodes for Plan, Build, Verify, Ship.
- Inner supervisor implemented as a LangGraph subgraph invoked from the Build node.
- State persisted via LangGraph's checkpointer, backed by our own Postgres tables (not the built-in SQLite checkpointer — see ADR-0006 principle that all state is auditable).
- Agent invocations go through a thin wrapper that persists `agent_turn` rows before returning to LangGraph.

## Consequences

- **Ergonomic for LLM/agent code.** State passing, tool routing, and streaming are first-class. Prompt iteration is fast.
- **Python-native.** No cross-language boundary between orchestrator and agents.
- **Checkpointing is there but limited.** LangGraph's checkpointer handles graph state; it doesn't give us Temporal-grade determinism or replay. We add durable session state on top via our own `task_session` and `agent_turn` tables.
- **Weaker durability guarantees than Temporal.** A process crash mid-node may leave dangling state that needs reconciliation. Acceptable at Phase 0-2 scale; may bite in Phase 3+.
- **No first-class timers or long timers.** For long-running tasks (waiting on a human for hours), we implement our own polling on top of the session table.

## Alternatives considered

- **Temporal.** Stronger durability semantics (deterministic replay, timers, cancellation, workflow versioning). Heavier runtime, less LLM-native ergonomics, more infra (Temporal cluster). Right answer if durability is the top constraint; likely a Phase 3 migration if scale demands it. Keeping the agent code decoupled from LangGraph specifics (via a thin orchestrator interface in `services/orchestrator/`) preserves that option.
- **Raw asyncio + custom state machine.** Maximum flexibility, no dependency. Reinvents everything LangGraph gives us for free. Rejected.
- **Prefect / Airflow.** Optimized for batch data pipelines, not agentic LLM loops. Wrong shape.
- **AutoGen / CrewAI.** Higher-level agent frameworks. Too opinionated about agent-to-agent messaging patterns; we want to design that ourselves.

## References

- LangGraph docs: https://langchain-ai.github.io/langgraph/
- Strategy doc §3.1 (supervisor pattern), §3.6 (durable state)
- Related ADRs: ADR-0005 (supervisor pattern), ADR-0006 (verifier/reviewer split)
