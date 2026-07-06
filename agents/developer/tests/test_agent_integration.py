"""End-to-end DeveloperAgent test (card 08): real LLM, real sandbox, real Verifier,
real Context Provider, against a demo target repo.

Requires the full service stack plus a demo repo, so on top of the ``integration``
marker it skips unless every env var below is set:

- ``ANTHROPIC_API_KEY``
- ``SANDBOX_URL``, ``VERIFIER_URL``, ``CONTEXT_PROVIDER_URL`` — running services
- ``DEMO_REPO_PATH`` — host path to the demo TS repo (``target-repos/demo-lib``)
"""

import os
import uuid

import httpx
import pytest
from developer.agent import DeveloperAgent
from developer.sandbox_client import SandboxClient
from developer.tools import DeveloperTools

_REQUIRED_ENV = ("ANTHROPIC_API_KEY", "SANDBOX_URL", "VERIFIER_URL", "CONTEXT_PROVIDER_URL",
                 "DEMO_REPO_PATH")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not all(os.environ.get(var) for var in _REQUIRED_ENV),
        reason=f"needs {', '.join(_REQUIRED_ENV)}",
    ),
]


class _ListRecorder:
    def __init__(self) -> None:
        self.turns: list[dict[str, object]] = []

    async def __call__(self, **kwargs: object) -> None:
        self.turns.append(dict(kwargs))


@pytest.mark.asyncio
async def test_simple_task_completes_end_to_end() -> None:
    repo_path = os.environ["DEMO_REPO_PATH"]
    plan: dict[str, object] = {
        "subtasks": [
            {
                "title": "Add sum helper",
                "description": (
                    "Add `export function sum(a: number, b: number): number` to src/math.ts "
                    "and a vitest test covering it."
                ),
                "acceptance": "build, typecheck, tests, and lint all pass",
            }
        ],
        "risks": [],
        "estimated_files": ["src/math.ts", "src/math.test.ts"],
    }

    async with httpx.AsyncClient(timeout=300.0) as http:
        sandbox = SandboxClient(os.environ["SANDBOX_URL"], http=http)
        tools = DeveloperTools(
            context_provider_url=os.environ["CONTEXT_PROVIDER_URL"],
            sandbox_url=os.environ["SANDBOX_URL"],
            verifier_url=os.environ["VERIFIER_URL"],
            repo=repo_path,
            http=http,
        )
        recorder = _ListRecorder()
        agent = DeveloperAgent(recorder=recorder, tools=tools)
        handle = await sandbox.spawn(repo_path)
        try:
            result = await agent.build(plan, handle, uuid.uuid4())
        finally:
            await sandbox.destroy(handle.id)

    assert result.status == "passed", f"loop ended {result.status}: {result.verifier_facts}"
    assert "sum" in result.diff
    assert result.verifier_facts.tests.status == "pass"
    assert recorder.turns, "every iteration must persist an agent_turn"
