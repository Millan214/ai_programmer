"""Adapts ``DeveloperAgent`` to the dict-returning ``DeveloperProtocol`` and owns the
sandbox lifecycle around one build.

Spawn happens here (the graph node shouldn't know sandboxes exist); the sandbox is
*not* destroyed on success — the Verify node still needs the worktree on disk, so
teardown belongs to the orchestrator's end-of-run cleanup (``sandbox_cleanup`` hook,
wired in ``orchestrator.main``). On an exception mid-loop the run dies before Verify,
so the adapter destroys eagerly rather than leak a container.

``DeveloperTools`` is built per call, not at wiring time: the Context Provider needs
the repo identifier, which is per-task state.

Sandbox setup commands (dependency install) are resolved here rather than in the
sandbox service: the sandbox stays toolchain-agnostic, and *what* to install is a
target-repo property the developer layer owns. Phase 0 targets pnpm/TS repos, so the
default installs with the committed lockfile; ``SANDBOX_SETUP_COMMANDS`` (a JSON list
of argv lists) overrides it for other stacks or to disable install (``[]``).
"""

import json
import os
import uuid
from typing import cast

import httpx
from orchestrator.protocols import EditsDict, PlanDict, TurnRecorder

from developer.agent import DeveloperAgent
from developer.models import DeveloperError
from developer.sandbox_client import SandboxClient
from developer.tools import DeveloperTools

_HTTP_TIMEOUT_S = 180.0
SETUP_COMMANDS_ENV = "SANDBOX_SETUP_COMMANDS"
DEFAULT_SETUP_COMMANDS: list[list[str]] = [["pnpm", "install", "--frozen-lockfile"]]


def resolve_setup_commands() -> list[list[str]]:
    """The commands a fresh sandbox runs to install the target repo's deps.

    Default targets a pnpm/TS repo; ``SANDBOX_SETUP_COMMANDS`` (a JSON list of argv
    lists) overrides — including ``[]`` to disable install for a repo that needs none.
    """
    raw = os.environ.get(SETUP_COMMANDS_ENV)
    if raw is None:
        return DEFAULT_SETUP_COMMANDS
    try:
        parsed: object = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DeveloperError(f"{SETUP_COMMANDS_ENV} is not valid JSON: {exc}") from exc
    if not isinstance(parsed, list):
        raise DeveloperError(f"{SETUP_COMMANDS_ENV} must be a JSON list of string lists")
    commands: list[list[str]] = []
    for command in cast("list[object]", parsed):
        if not isinstance(command, list) or not all(
            isinstance(arg, str) for arg in cast("list[object]", command)
        ):
            raise DeveloperError(f"{SETUP_COMMANDS_ENV} must be a JSON list of string lists")
        commands.append(cast("list[str]", command))
    return commands


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
            handle = await sandbox.spawn(repo, setup_commands=resolve_setup_commands())
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
