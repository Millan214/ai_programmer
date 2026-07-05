"""Entry point: run a submitted task through the outer FSM.

Card 04 wires the real ``PlannerAgent`` in place of ``FakePlanner`` whenever an
Anthropic API key is available; otherwise we fall back to the fake so the graph still
runs end-to-end in offline environments (CI without secrets, local `make test` without
a network, etc.).
"""

import os
import uuid

from orchestrator.graph import Orchestrator
from orchestrator.persistence import OrchestratorPersistence
from orchestrator.protocols import (
    DeveloperProtocol,
    FakeDeveloper,
    FakePlanner,
    FakeVerifier,
    PlannerProtocol,
    VerifierProtocol,
)


def _build_planner(persistence: OrchestratorPersistence) -> PlannerProtocol:
    """Real Planner if we have credentials, fake otherwise (never breaks import time)."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return FakePlanner(recorder=persistence.record_agent_turn)
    # Imported lazily so the orchestrator package doesn't require ``platform-planner``
    # at import time (avoids a cycle: planner already depends on orchestrator protocols).
    from planner.adapter import PlannerProtocolAdapter
    from planner.agent import PlannerAgent

    agent = PlannerAgent(recorder=persistence.record_agent_turn)
    return PlannerProtocolAdapter(agent)


def default_orchestrator() -> Orchestrator:
    """Wire the graph with the real Planner (if creds are available) plus Phase 0 fakes."""
    persistence = OrchestratorPersistence()
    planner: PlannerProtocol = _build_planner(persistence)
    developer: DeveloperProtocol = FakeDeveloper()
    verifier: VerifierProtocol = FakeVerifier()
    return Orchestrator(
        planner=planner,
        developer=developer,
        verifier=verifier,
        persistence=persistence,
    )


async def run(task_id: uuid.UUID) -> None:
    """Load the task, drive it through Plan/Build/Verify/Ship, and persist the outcome."""
    await default_orchestrator().execute(task_id)
