"""Entry point: run a submitted task through the outer FSM with the Phase 0 fakes."""

import uuid

from orchestrator.graph import Orchestrator
from orchestrator.persistence import OrchestratorPersistence
from orchestrator.protocols import FakeDeveloper, FakePlanner, FakeVerifier


def default_orchestrator() -> Orchestrator:
    """Wire the graph with Phase 0 fakes and Postgres-backed persistence."""
    return Orchestrator(
        planner=FakePlanner(),
        developer=FakeDeveloper(),
        verifier=FakeVerifier(),
        persistence=OrchestratorPersistence(),
    )


async def run(task_id: uuid.UUID) -> None:
    """Load the task, drive it through Plan/Build/Verify/Ship, and persist the outcome."""
    await default_orchestrator().execute(task_id)
