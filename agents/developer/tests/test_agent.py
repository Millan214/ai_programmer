"""DeveloperAgent unit tests (card 08). No network, no Docker, no DB — the Anthropic
client is scripted, the tools are an in-memory fake, and the ``TurnRecorder`` captures
what each ``agent_turn`` row would carry.
"""

import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from anthropic.types import Message, TextBlock, ToolUseBlock, Usage
from developer.agent import DeveloperAgent
from developer.models import BuildResult
from sandbox.models import SandboxHandle
from verifier.models import (
    BuildResult as VerifierBuildResult,
)
from verifier.models import (
    LintResult,
    Status,
    TestResult,
    TypecheckResult,
    VerifierResult,
)

_HANDLE = SandboxHandle(id="sb-test", worktree_path=Path("/tmp/sb-test"), container_id="c0")


class _FakeRecorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(
        self,
        *,
        session_id: uuid.UUID,
        agent: str,
        model: str,
        prompt_version: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: Decimal | None,
        tool_calls: dict[str, object] | None = None,
        output_ref: str | None = None,
    ) -> None:
        self.calls.append(
            {
                "session_id": session_id,
                "agent": agent,
                "model": model,
                "prompt_version": prompt_version,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": cost_usd,
                "tool_calls": tool_calls,
                "output_ref": output_ref,
            }
        )


class _StubClient:
    """AsyncAnthropic stand-in. Each call pops the next scripted response."""

    def __init__(self, responses: list[Message]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []
        self.messages = self

    async def create(self, **kwargs: Any) -> Message:
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("StubClient exhausted — test scripted fewer responses than calls")
        return self._responses.pop(0)


def _message(*blocks: TextBlock | ToolUseBlock, tokens: tuple[int, int] = (100, 50)) -> Message:
    return Message.model_construct(
        id="msg_test",
        type="message",
        role="assistant",
        model="claude-sonnet-4-6",
        content=list(blocks),
        stop_reason="tool_use",
        stop_sequence=None,
        usage=Usage.model_construct(input_tokens=tokens[0], output_tokens=tokens[1]),
    )


def _tool_use(name: str, args: dict[str, object], *, block_id: str = "tu_1") -> ToolUseBlock:
    return ToolUseBlock(type="tool_use", id=block_id, name=name, input=args)


def _text(text: str) -> TextBlock:
    return TextBlock(type="text", text=text, citations=None)


def _facts(
    *,
    build: Status = "pass",
    typecheck: Status = "pass",
    tests: Status = "pass",
    lint: Status = "pass",
) -> VerifierResult:
    return VerifierResult(
        build=VerifierBuildResult(status=build),
        typecheck=TypecheckResult(status=typecheck),
        tests=TestResult(status=tests),
        lint=LintResult(status=lint),
    )


class _FakeTools:
    def __init__(self, verifier_results: list[VerifierResult] | None = None) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self._verifier_results = list(verifier_results or [])

    async def retrieve(self, query: str, mode: str) -> str:
        self.calls.append(("retrieve", (query, mode)))
        return "retrieved context"

    async def read_file(self, path: str, sandbox: SandboxHandle) -> str:
        self.calls.append(("read_file", (path,)))
        return "file content"

    async def edit_file(self, path: str, content: str, sandbox: SandboxHandle) -> None:
        self.calls.append(("edit_file", (path,)))

    async def run_verifier(self, sandbox: SandboxHandle) -> VerifierResult:
        self.calls.append(("run_verifier", ()))
        if not self._verifier_results:
            raise AssertionError("no scripted verifier results left")
        return self._verifier_results.pop(0)

    async def get_diff(self, sandbox: SandboxHandle) -> str:
        return "--- fake diff ---"


_PLAN: dict[str, object] = {
    "subtasks": [
        {"title": "Add sum", "description": "Add sum() to src/math.ts", "acceptance": "tests pass"}
    ],
    "risks": [],
    "estimated_files": ["src/math.ts"],
}


def _agent(
    recorder: _FakeRecorder,
    client: _StubClient,
    tools: _FakeTools,
    *,
    max_iterations: int = 15,
    token_budget: int = 1_000_000,
) -> DeveloperAgent:
    return DeveloperAgent(
        recorder=recorder,
        tools=tools,
        client=client,  # type: ignore[arg-type]
        model="claude-sonnet-4-6",
        max_iterations=max_iterations,
        token_budget=token_budget,
    )


@pytest.mark.asyncio
async def test_two_iteration_path_exits_passed_and_records_each_turn() -> None:
    recorder = _FakeRecorder()
    client = _StubClient(
        [
            _message(_tool_use("retrieve", {"query": "math module", "mode": "symbol"})),
            _message(_tool_use("edit_file", {"path": "src/math.ts", "content": "export {}"})),
        ]
    )
    tools = _FakeTools(verifier_results=[_facts()])

    result = await _agent(recorder, client, tools).build(_PLAN, _HANDLE, uuid.uuid4())

    assert isinstance(result, BuildResult)
    assert result.status == "passed"
    assert result.diff == "--- fake diff ---"
    assert result.verifier_facts.build.status == "pass"
    # The edit auto-ran the verifier; the loop exited green without a third model call.
    assert [name for name, _ in tools.calls] == ["retrieve", "edit_file", "run_verifier"]

    # Two iteration turns + one final summary turn (carries the diff, zero tokens).
    assert len(recorder.calls) == 3
    turn = recorder.calls[0]
    assert turn["agent"] == "developer"
    assert turn["model"] == "claude-sonnet-4-6"
    assert turn["prompt_version"].startswith("developer/build@")
    assert isinstance(turn["cost_usd"], Decimal) and turn["cost_usd"] > Decimal(0)
    assert turn["tool_calls"] == {
        "calls": [{"tool": "retrieve", "input": {"query": "math module", "mode": "symbol"}}]
    }
    # The final turn persists the diff and exit status for the audit trail / e2e assertions.
    final = recorder.calls[-1]
    assert final["output_ref"] == "--- fake diff ---"
    assert final["tool_calls"] == {"final_status": "passed"}
    assert final["input_tokens"] == 0


@pytest.mark.asyncio
async def test_red_verifier_keeps_looping_until_green() -> None:
    recorder = _FakeRecorder()
    client = _StubClient(
        [
            _message(_tool_use("edit_file", {"path": "src/math.ts", "content": "bad"})),
            _message(_tool_use("edit_file", {"path": "src/math.ts", "content": "good"})),
        ]
    )
    tools = _FakeTools(verifier_results=[_facts(tests="fail"), _facts()])

    result = await _agent(recorder, client, tools).build(_PLAN, _HANDLE, uuid.uuid4())

    assert result.status == "passed"
    assert len(recorder.calls) == 3  # 2 iterations + final summary
    assert result.verifier_facts.tests.status == "pass"


@pytest.mark.asyncio
async def test_same_tool_and_args_three_times_exits_stuck() -> None:
    recorder = _FakeRecorder()
    repeated = {"path": "src/math.ts"}
    client = _StubClient(
        [
            _message(_tool_use("read_file", dict(repeated))),
            _message(_tool_use("read_file", dict(repeated))),
            _message(_tool_use("read_file", dict(repeated))),
        ]
    )
    tools = _FakeTools()

    result = await _agent(recorder, client, tools).build(_PLAN, _HANDLE, uuid.uuid4())

    assert result.status == "stuck"
    assert len(recorder.calls) == 4  # 3 iterations + final summary
    # The verifier never ran; the facts say so instead of pretending.
    assert result.verifier_facts.build.status == "skip"


@pytest.mark.asyncio
async def test_token_budget_breach_exits_budget_exceeded() -> None:
    recorder = _FakeRecorder()
    client = _StubClient(
        [_message(_tool_use("retrieve", {"query": "x", "mode": "symbol"}), tokens=(90, 20))]
    )
    tools = _FakeTools()

    result = await _agent(recorder, client, tools, token_budget=100).build(
        _PLAN, _HANDLE, uuid.uuid4()
    )

    assert result.status == "budget_exceeded"
    # The breaching call is still recorded — the spend happened (principle 4) — plus the
    # final summary turn.
    assert len(recorder.calls) == 2
    # No tool ran after the breach.
    assert tools.calls == []


@pytest.mark.asyncio
async def test_iteration_cap_exits_max_iterations() -> None:
    recorder = _FakeRecorder()
    client = _StubClient(
        [
            _message(_tool_use("retrieve", {"query": "first", "mode": "symbol"})),
            _message(_tool_use("retrieve", {"query": "second", "mode": "explore"})),
        ]
    )
    tools = _FakeTools()

    result = await _agent(recorder, client, tools, max_iterations=2).build(
        _PLAN, _HANDLE, uuid.uuid4()
    )

    assert result.status == "max_iterations"
    assert len(recorder.calls) == 3  # 2 iterations + final summary


@pytest.mark.asyncio
async def test_text_only_response_is_nudged_not_trusted() -> None:
    """The model claiming success is not an exit condition — only a green verifier is."""
    recorder = _FakeRecorder()
    client = _StubClient(
        [
            _message(_text("All done, everything passes!")),
            _message(_tool_use("edit_file", {"path": "src/math.ts", "content": "export {}"})),
        ]
    )
    tools = _FakeTools(verifier_results=[_facts()])

    result = await _agent(recorder, client, tools).build(_PLAN, _HANDLE, uuid.uuid4())

    assert result.status == "passed"
    assert len(recorder.calls) == 3  # text-only turn + edit turn + final summary
    # The conversation history carries the nudge that followed the text-only turn.
    history = client.calls[1]["messages"]
    assert any("without a green verifier run" in str(m["content"]) for m in history)
