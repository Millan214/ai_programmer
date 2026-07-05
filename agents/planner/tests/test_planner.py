"""PlannerAgent unit tests. No network, no DB — Anthropic client is stubbed and the
``TurnRecorder`` is a small in-memory fake so we can assert what the row would carry.
"""

import json
import uuid
from decimal import Decimal
from typing import Any

import pytest
from anthropic.types import Message, TextBlock, Usage
from planner.agent import PlannerAgent
from planner.models import Plan, PlannerOutputError


class _RecordedTurn(dict[str, Any]):
    pass


class _FakeRecorder:
    """Captures every ``TurnRecorder`` call for assertions."""

    def __init__(self) -> None:
        self.calls: list[_RecordedTurn] = []

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
            _RecordedTurn(
                session_id=session_id,
                agent=agent,
                model=model,
                prompt_version=prompt_version,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                tool_calls=tool_calls,
                output_ref=output_ref,
            )
        )


def _make_message(text: str, *, input_tokens: int = 120, output_tokens: int = 240) -> Message:
    """Build a real ``anthropic.types.Message`` — easier than mocking the whole shape."""
    return Message.model_construct(
        id="msg_test",
        type="message",
        role="assistant",
        model="claude-opus-4-7",
        content=[TextBlock(type="text", text=text, citations=None)],
        stop_reason="end_turn",
        stop_sequence=None,
        usage=Usage.model_construct(input_tokens=input_tokens, output_tokens=output_tokens),
    )


class _StubClient:
    """Anthropic AsyncAnthropic stand-in. Each call pops the next scripted response."""

    def __init__(self, responses: list[Message]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []
        self.messages = self  # ``client.messages.create(...)`` — collapse the namespace.

    async def create(self, **kwargs: Any) -> Message:
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("StubClient exhausted — test scripted fewer responses than calls")
        return self._responses.pop(0)


_VALID_PLAN_JSON = json.dumps(
    {
        "subtasks": [
            {
                "title": "Add hasPermission helper",
                "description": "Introduce hasPermission(user, action) in auth/perms.py.",
                "acceptance": "Unit tests for hasPermission pass.",
            }
        ],
        "risks": ["assumed no existing helper of same name"],
        "estimated_files": ["auth/perms.py", "tests/test_perms.py"],
    }
)


@pytest.mark.asyncio
async def test_plan_happy_path_parses_and_records_turn() -> None:
    recorder = _FakeRecorder()
    client = _StubClient([_make_message(_VALID_PLAN_JSON, input_tokens=120, output_tokens=240)])
    agent = PlannerAgent(recorder=recorder, client=client, model="claude-opus-4-7")  # type: ignore[arg-type]
    session_id = uuid.uuid4()

    plan = await agent.plan("add a hasPermission(user, action) helper", session_id)

    assert isinstance(plan, Plan)
    assert plan.subtasks[0].title == "Add hasPermission helper"
    assert plan.estimated_files == ["auth/perms.py", "tests/test_perms.py"]

    assert len(client.calls) == 1
    assert client.calls[0]["model"] == "claude-opus-4-7"

    assert len(recorder.calls) == 1
    turn = recorder.calls[0]
    assert turn["session_id"] == session_id
    assert turn["agent"] == "planner"
    assert turn["model"] == "claude-opus-4-7"
    assert turn["prompt_version"].startswith("planner/plan@")
    assert turn["input_tokens"] == 120
    assert turn["output_tokens"] == 240
    # Cost is real (per-token pricing table) — non-zero for known models.
    assert isinstance(turn["cost_usd"], Decimal)
    assert turn["cost_usd"] > Decimal(0)


@pytest.mark.asyncio
async def test_plan_retries_once_on_malformed_json() -> None:
    recorder = _FakeRecorder()
    client = _StubClient(
        [
            _make_message("not json at all", input_tokens=100, output_tokens=50),
            _make_message(_VALID_PLAN_JSON, input_tokens=110, output_tokens=200),
        ]
    )
    agent = PlannerAgent(recorder=recorder, client=client, model="claude-opus-4-7")  # type: ignore[arg-type]

    plan = await agent.plan("some task", uuid.uuid4())

    assert isinstance(plan, Plan)
    assert len(client.calls) == 2, "expected exactly one retry"
    # Only the successful call is recorded — a failed parse never persists a turn.
    assert len(recorder.calls) == 1
    assert recorder.calls[0]["input_tokens"] == 110
    assert recorder.calls[0]["output_tokens"] == 200


@pytest.mark.asyncio
async def test_plan_raises_after_two_malformed_responses() -> None:
    recorder = _FakeRecorder()
    client = _StubClient(
        [
            _make_message("still not json"),
            _make_message("also not json"),
        ]
    )
    agent = PlannerAgent(recorder=recorder, client=client, model="claude-opus-4-7")  # type: ignore[arg-type]

    with pytest.raises(PlannerOutputError):
        await agent.plan("some task", uuid.uuid4())

    assert len(client.calls) == 2
    assert recorder.calls == []


@pytest.mark.asyncio
async def test_plan_raises_when_json_shape_wrong() -> None:
    recorder = _FakeRecorder()
    # Valid JSON but wrong schema — no subtasks/risks/estimated_files.
    bad_payload = json.dumps({"something": "else"})
    client = _StubClient([_make_message(bad_payload), _make_message(bad_payload)])
    agent = PlannerAgent(recorder=recorder, client=client, model="claude-opus-4-7")  # type: ignore[arg-type]

    with pytest.raises(PlannerOutputError):
        await agent.plan("some task", uuid.uuid4())

    assert len(client.calls) == 2
