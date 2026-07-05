"""Adapts the Pydantic-returning ``PlannerAgent`` to the dict-returning ``PlannerProtocol``.

Card 03 pinned the protocol at ``PlanDict`` on purpose (see ``orchestrator.protocols``
docstring: the graph carries dicts and Postgres stores them as JSONB). Card 04's
``PlannerAgent.plan`` returns the richer ``Plan`` model — useful for callers that want
typed access. This adapter closes that gap at the graph seam without leaking Pydantic
into the orchestrator's protocol module.
"""

import uuid

from orchestrator.protocols import PlanDict

from planner.agent import PlannerAgent


class PlannerProtocolAdapter:
    def __init__(self, agent: PlannerAgent) -> None:
        self._agent = agent

    async def plan(self, task_description: str, session_id: uuid.UUID) -> PlanDict:
        plan = await self._agent.plan(task_description, session_id)
        return plan.model_dump()
