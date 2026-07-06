"""Adapts ``DeveloperAgent`` to the dict-returning ``DeveloperProtocol`` and owns the
sandbox lifecycle around one build.

Spawn happens here (the graph node shouldn't know sandboxes exist); the sandbox is
*not* destroyed on success — the Verify node still needs the worktree on disk, so
teardown belongs to the orchestrator's end-of-run cleanup (``sandbox_cleanup`` hook,
wired in ``orchestrator.main``). On an exception mid-loop the run dies before Verify,
so the adapter destroys eagerly rather than leak a container.

``DeveloperTools`` is built per call, not at wiring time: the Context Provider needs
the repo identifier, which is per-task state.
"""

import uuid

import httpx
from orchestrator.protocols import EditsDict, PlanDict, TurnRecorder

from developer.agent import DeveloperAgent
from developer.sandbox_client import SandboxClient
from developer.tools import DeveloperTools

_HTTP_TIMEOUT_S = 180.0


class DeveloperProtocolAdapter:
    def __init__(
        self,
        *,
        recorder: TurnRecorder,
        context_provider_url: str,
        sandbox_url: str,
        verifier_url: str,
    ) -> None:
        self._recorder = recorder
        self._context_provider_url = context_provider_url
        self._sandbox_url = sandbox_url
        self._verifier_url = verifier_url

    async def build(self, plan: PlanDict, repo: str, session_id: uuid.UUID) -> EditsDict:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_S) as http:
            sandbox = SandboxClient(self._sandbox_url, http=http)
            tools = DeveloperTools(
                context_provider_url=self._context_provider_url,
                sandbox_url=self._sandbox_url,
                verifier_url=self._verifier_url,
                repo=repo,
                session_id=session_id,
                http=http,
            )
            agent = DeveloperAgent(recorder=self._recorder, tools=tools)
            handle = await sandbox.spawn(repo)
            try:
                result = await agent.build(plan, handle, session_id)
            except BaseException:
                await sandbox.destroy(handle.id)
                raise
            return {
                "status": result.status,
                "diff": result.diff,
                "worktree_path": str(handle.worktree_path),
                "sandbox_id": handle.id,
                "verifier_facts": result.verifier_facts.model_dump(),
            }
