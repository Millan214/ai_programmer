from typing import TypedDict

# Phase 0 does not enforce a budget (ADR-0005's circuit-breaker is Phase 2); the field
# is carried through state so the shape is stable when enforcement lands.
DEFAULT_BUDGET_REMAINING = 0.0


class TaskState(TypedDict):
    """State threaded through the outer Plan/Build/Verify/Ship graph.

    The six domain fields (``task_id``, ``phase``, ``plan``, ``edits``,
    ``verifier_facts``, ``budget_remaining``) are from card 03's spec.
    ``session_id``, ``task_description``, and ``repo`` are added as plumbing: the first
    links every ``agent_turn`` to its ``task_session`` (FK), the second is the Planner's
    input, the third tells the Developer what to spawn a sandbox from (card 08).
    """

    task_id: str
    session_id: str
    task_description: str
    repo: str
    phase: str
    plan: dict[str, object] | None
    edits: dict[str, object] | None
    verifier_facts: dict[str, object] | None
    budget_remaining: float
