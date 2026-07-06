"""Entry point: run a submitted task through the outer FSM.

Card 04 wires the real ``PlannerAgent`` in place of ``FakePlanner`` whenever an
Anthropic API key is available; card 05 does the same for the Verifier, keyed off
``VERIFIER_URL``; card 08 the same for the Developer, keyed off the full service trio
(``SANDBOX_URL``/``VERIFIER_URL``/``CONTEXT_PROVIDER_URL`` plus the API key). All fall
back to their fakes so the graph still runs end-to-end in offline environments (CI
without secrets, local `make test` without a network, etc.).
"""

import os
import uuid

import httpx

from orchestrator.graph import Orchestrator
from orchestrator.persistence import OrchestratorPersistence
from orchestrator.protocols import (
    DeveloperProtocol,
    FakeDeveloper,
    FakePlanner,
    FakeVerifier,
    PlannerProtocol,
    SandboxCleanup,
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

    The real client needs ``edits["worktree_path"]``, which only the real Developer
    (card 08) produces. When the Developer is fake, this stays fake too even if
    ``VERIFIER_URL`` is set — there's nothing on disk for the real Verifier to inspect.
    """
    verifier_url = os.environ.get("VERIFIER_URL")
    if not verifier_url or not _developer_env():
        return FakeVerifier()
    return VerifierHttpClient(verifier_url)


def _developer_env() -> tuple[str, str, str] | None:
    """The service trio the real Developer needs, or None if any is missing."""
    sandbox_url = os.environ.get("SANDBOX_URL")
    verifier_url = os.environ.get("VERIFIER_URL")
    context_provider_url = os.environ.get("CONTEXT_PROVIDER_URL")
    if not (
        os.environ.get("ANTHROPIC_API_KEY") and sandbox_url and verifier_url
        and context_provider_url
    ):
        return None
    return sandbox_url, verifier_url, context_provider_url


def _build_developer(
    persistence: OrchestratorPersistence,
) -> tuple[DeveloperProtocol, SandboxCleanup | None]:
    """Real Developer if the whole service trio is configured, fake otherwise.

    Returns the matching sandbox-cleanup hook alongside — only a real Developer leaves
    a sandbox behind for the orchestrator to tear down at end of run.
    """
    env = _developer_env()
    if env is None:
        return FakeDeveloper(recorder=persistence.record_agent_turn), None
    sandbox_url, verifier_url, context_provider_url = env
    # Lazy import for the same reason as the planner's: developer depends on
    # orchestrator protocols, never the reverse.
    from developer.adapter import DeveloperProtocolAdapter

    adapter = DeveloperProtocolAdapter(
        recorder=persistence.record_agent_turn,
        context_provider_url=context_provider_url,
        sandbox_url=sandbox_url,
        verifier_url=verifier_url,
    )

    async def cleanup(sandbox_id: str) -> None:
        async with httpx.AsyncClient(timeout=120.0) as http:
            await http.delete(f"{sandbox_url.rstrip('/')}/sandboxes/{sandbox_id}")

    return adapter, cleanup


def default_orchestrator() -> Orchestrator:
    """Wire the graph with the real Planner/Developer/Verifier (if configured) plus fakes."""
    persistence = OrchestratorPersistence()
    planner: PlannerProtocol = _build_planner(persistence)
    developer, sandbox_cleanup = _build_developer(persistence)
    verifier: VerifierProtocol = _build_verifier()
    return Orchestrator(
        planner=planner,
        developer=developer,
        verifier=verifier,
        persistence=persistence,
        sandbox_cleanup=sandbox_cleanup,
    )


async def run(task_id: uuid.UUID) -> None:
    """Load the task, drive it through Plan/Build/Verify/Ship, and persist the outcome."""
    await default_orchestrator().execute(task_id)
