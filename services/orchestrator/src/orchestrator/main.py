"""Entry point: run a submitted task through the outer FSM.

Card 04 wires the real ``PlannerAgent`` in place of ``FakePlanner`` whenever an
Anthropic API key is available; card 05 does the same for the Verifier, keyed off
``VERIFIER_URL``. Both fall back to their fakes so the graph still runs end-to-end in
offline environments (CI without secrets, local `make test` without a network, etc.).
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
from orchestrator.verifier_client import VerifierHttpClient


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


def _build_verifier() -> VerifierProtocol:
    """Real Verifier if a service URL is configured, fake otherwise.

    The real client needs ``edits["worktree_path"]``, which only exists once card 08's
    Developer agent produces real edits against a real sandbox checkout (cards 06/07).
    Until then this stays fake even when ``VERIFIER_URL`` is set in a partially-deployed
    environment — there's nothing on disk yet for the real Verifier to inspect.
    """
    verifier_url = os.environ.get("VERIFIER_URL")
    if not verifier_url:
        return FakeVerifier()
    return VerifierHttpClient(verifier_url)


def default_orchestrator() -> Orchestrator:
    """Wire the graph with the real Planner/Verifier (if configured) plus Phase 0 fakes."""
    persistence = OrchestratorPersistence()
    planner: PlannerProtocol = _build_planner(persistence)
    developer: DeveloperProtocol = FakeDeveloper()
    verifier: VerifierProtocol = _build_verifier()
    return Orchestrator(
        planner=planner,
        developer=developer,
        verifier=verifier,
        persistence=persistence,
    )


async def run(task_id: uuid.UUID) -> None:
    """Load the task, drive it through Plan/Build/Verify/Ship, and persist the outcome."""
    await default_orchestrator().execute(task_id)
