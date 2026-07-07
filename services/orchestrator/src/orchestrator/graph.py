"""The outer FSM: Plan -> Build -> Verify -> Ship.

Phase 0 is strictly forward (ADR-0005): a failing Verify terminates the run in
``failed_verify`` rather than looping back. Back-edges and the inner supervisor loop
arrive in Phase 2.
"""

# LangGraph 1.2 ships no stubs for `langgraph.graph` and types StateGraph.add_node /
# compile with partially-unknown generics (Runnable[..., Any]), which trip pyright
# strict's reportMissingTypeStubs and reportUnknownMemberType at every call site here.
# Both rules are disabled for this file only — it is pure LangGraph glue, fully exercised
# by tests/test_graph.py; our own logic keeps strict typing.
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false

import uuid
from typing import cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from platform_telemetry import set_task_context, traced

from orchestrator.persistence import PersistenceProtocol
from orchestrator.protocols import (
    DeveloperProtocol,
    PlannerProtocol,
    SandboxCleanup,
    VerifierProtocol,
)
from orchestrator.state import TaskState

# Fake PR URL host — the real merge coordinator is Phase 1+. ``.invalid`` is reserved
# by RFC 2606 and can never resolve, so a stray link is obviously fake.
_FAKE_PR_HOST = "https://example.invalid/pr"


def _verify_passed(facts: dict[str, object] | None) -> bool:
    # Gate ship on the correctness-critical facts the Verifier reports (R3): build,
    # typecheck, and tests must all pass — previously only build+tests were checked, so a
    # change with type errors could ship. Lint is reported but *not* gated in Phase 0:
    # style issues shouldn't block a green change, and a lint gate is a policy call that
    # belongs to Phase 2's Reviewer.
    facts = facts or {}
    return all(facts.get(check) == "pass" for check in ("build", "typecheck", "tests"))


class Orchestrator:
    """Owns the agent protocol impls and persistence, and drives one task run."""

    def __init__(
        self,
        planner: PlannerProtocol,
        developer: DeveloperProtocol,
        verifier: VerifierProtocol,
        persistence: PersistenceProtocol,
        sandbox_cleanup: SandboxCleanup | None = None,
    ) -> None:
        self._planner = planner
        self._developer = developer
        self._verifier = verifier
        self._persistence = persistence
        self._sandbox_cleanup = sandbox_cleanup
        # Compile the graph once (R16): the topology is fixed, and every ``execute`` shared
        # the same MemorySaver anyway (runs are isolated by ``thread_id``, not by graph).
        self._compiled = self.build_graph()

    @traced("orchestrator.plan")
    async def _plan_node(self, state: TaskState) -> dict[str, object]:
        session_id = uuid.UUID(state["session_id"])
        # The planner (real or fake) writes its own ``agent_turn`` row via the
        # ``TurnRecorder`` it was constructed with; the graph only advances the phase.
        plan = await self._planner.plan(state["task_description"], session_id)
        await self._persistence.advance_phase(session_id, "plan")
        return {"plan": plan, "phase": "plan"}

    @traced("orchestrator.build")
    async def _build_node(self, state: TaskState) -> dict[str, object]:
        session_id = uuid.UUID(state["session_id"])
        # Like the planner, the developer (real or fake) writes its own ``agent_turn``
        # rows — one per ReAct iteration — via its ``TurnRecorder`` (card 08).
        edits = await self._developer.build(state["plan"] or {}, state["repo"], session_id)
        await self._persistence.advance_phase(session_id, "build")
        return {"edits": edits, "phase": "build"}

    @traced("orchestrator.verify")
    async def _verify_node(self, state: TaskState) -> dict[str, object]:
        session_id = uuid.UUID(state["session_id"])
        # The real Verifier persists this run as a ``verifier_run`` row keyed on the
        # session (R2); the ``record_node`` turn below is just the phase transition.
        facts = await self._verifier.verify(state["edits"] or {}, session_id)
        await self._persistence.record_node(session_id, "verify", "verifier")
        return {"verifier_facts": facts, "phase": "verify"}

    @traced("orchestrator.ship")
    async def _ship_node(self, state: TaskState) -> dict[str, object]:
        pr_url = f"{_FAKE_PR_HOST}/{state['task_id']}"
        # The task row has no PR column in Phase 0 (card-01 schema), so the fake URL is
        # persisted as the ship turn's output_ref — auditable, no schema change.
        await self._persistence.record_node(
            uuid.UUID(state["session_id"]), "ship", "shipper", output_ref=pr_url
        )
        await self._persistence.set_task_status(uuid.UUID(state["task_id"]), "completed")
        return {"phase": "ship"}

    def _route_after_verify(self, state: TaskState) -> str:
        return "ship" if _verify_passed(state["verifier_facts"]) else END

    def build_graph(self) -> CompiledStateGraph[TaskState, None, TaskState, TaskState]:
        graph = StateGraph(TaskState)
        graph.add_node("plan", self._plan_node)
        graph.add_node("build", self._build_node)
        graph.add_node("verify", self._verify_node)
        graph.add_node("ship", self._ship_node)
        graph.add_edge(START, "plan")
        graph.add_edge("plan", "build")
        graph.add_edge("build", "verify")
        graph.add_conditional_edges("verify", self._route_after_verify, {"ship": "ship", END: END})
        graph.add_edge("ship", END)
        return graph.compile(checkpointer=MemorySaver())

    @traced("orchestrator.run")
    async def execute(self, task_id: uuid.UUID) -> None:
        # Pin the task on the contextvar so every span below — phases, agents, verifier —
        # carries it without threading task_id through call signatures. Provider setup is
        # done once at the process entry (``orchestrator.main.run``), not here, so calling
        # ``execute`` in a unit test doesn't mutate global tracing state.
        set_task_context(task_id)
        task = await self._persistence.load_task(task_id)
        session_id = await self._persistence.open_session(task_id)
        initial: TaskState = {
            "task_id": str(task_id),
            "session_id": str(session_id),
            "task_description": task["description"],
            "repo": task["repo"],
            "phase": "plan",
            "plan": None,
            "edits": None,
            "verifier_facts": None,
            "budget_remaining": task["budget_remaining"],
        }
        config: RunnableConfig = {"configurable": {"thread_id": str(task_id)}}
        try:
            final = cast(TaskState, await self._compiled.ainvoke(initial, config=config))
            # ship_node sets ``completed`` when it runs; if Verify failed the route
            # skipped ship and the run terminates in ``failed_verify`` (no back-edge in
            # Phase 0).
            if final["phase"] != "ship":
                await self._persistence.set_task_status(task_id, "failed_verify")
            await self._cleanup_sandbox(final["edits"])
        except Exception:
            # A raising planner/developer/verifier (e.g. a malformed LLM response or an
            # unreachable service) must not leave the task dangling in a non-terminal
            # state (R5). Mark it failed and re-raise so the caller/telemetry sees it.
            await self._persistence.set_task_status(task_id, "failed")
            raise
        finally:
            # Every terminal outcome — completed, failed_verify, or a crash — stamps the
            # session's ``ended_at`` (R5: it was never set by any path before).
            await self._persistence.close_session(session_id)

    async def _cleanup_sandbox(self, edits: dict[str, object] | None) -> None:
        # A real Developer leaves its sandbox alive so Verify could inspect the worktree
        # (see ``developer.adapter``); the run is over now, tear it down.
        if self._sandbox_cleanup is None:
            return
        sandbox_id = (edits or {}).get("sandbox_id")
        if isinstance(sandbox_id, str):
            await self._sandbox_cleanup(sandbox_id)
