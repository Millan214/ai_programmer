"""PlannerAgent — first real LLM agent in the platform.

Decomposes a task description into a structured ``Plan`` by prompting an Anthropic
Claude model. Persists the call as an ``agent_turn`` row through the ``TurnRecorder``
it was constructed with, so the row carries real model/tokens/cost rather than the
placeholder values card 03 used for its fake path.

Non-goals (per card 04): no tool use, no streaming, no prompt caching, no fallback
model, no plan-revision loop. Exactly one retry on a malformed JSON response, then
``PlannerOutputError`` bubbles.
"""

import json
import os
import uuid
from typing import cast

from anthropic import AsyncAnthropic
from anthropic.types import Message, TextBlock
from orchestrator.protocols import TurnRecorder
from platform_telemetry import add_llm_attributes, current_span, traced
from prompts.registry import PromptRef, active_version, render
from pydantic import ValidationError

from planner.models import Plan, PlannerOutputError
from planner.pricing import compute_cost

_DEFAULT_MODEL_ENV = "PLANNER_MODEL"
_DEFAULT_MODEL = "claude-opus-4-7"
_MAX_TOKENS = 2000
_PROMPT_AGENT = "planner"
_PROMPT_NAME = "plan"


class PlannerAgent:
    """Concrete Planner. Adapt via ``PlannerProtocolAdapter`` to satisfy the protocol."""

    def __init__(
        self,
        *,
        recorder: TurnRecorder,
        client: AsyncAnthropic | None = None,
        model: str | None = None,
    ) -> None:
        self._recorder = recorder
        self._client = client if client is not None else AsyncAnthropic()
        self._model = model or os.environ.get(_DEFAULT_MODEL_ENV) or _DEFAULT_MODEL

    @traced("planner.plan")
    async def plan(self, task_description: str, session_id: uuid.UUID) -> Plan:
        version = active_version(_PROMPT_AGENT, _PROMPT_NAME)
        prompt = render(
            PromptRef(agent=_PROMPT_AGENT, name=_PROMPT_NAME, version=version),
            task_description=task_description,
        )

        # Persist a turn for *every* model call, not just the successful one (R1 —
        # principle 4: every LLM call is a persisted event). Recording happens before
        # the parse so a call that produced un-parseable output is still on the ledger.
        response = await self._call_model(prompt)
        await self._record_turn(session_id, version, response)
        try:
            return _parse(_extract_text(response))
        except PlannerOutputError:
            # A ``max_tokens`` stop means the JSON was truncated — an identical re-roll
            # would truncate again, so surface it instead of burning a second call (R6).
            if response.stop_reason == "max_tokens":
                raise PlannerOutputError(
                    "planner output was truncated at max_tokens; increase the cap or "
                    "narrow the task rather than retrying"
                ) from None
            # Otherwise one retry — the prompt is explicit about JSON-only, so a re-roll
            # usually recovers. Any second failure is surfaced to the caller.
            response = await self._call_model(prompt)
            await self._record_turn(session_id, version, response)
            return _parse(_extract_text(response))

    async def _call_model(self, prompt: str) -> Message:
        return await self._client.messages.create(
            model=self._model,
            max_tokens=_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )

    async def _record_turn(
        self, session_id: uuid.UUID, prompt_version: str, response: Message
    ) -> None:
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost = compute_cost(self._model, input_tokens, output_tokens)
        full_version = f"{_PROMPT_AGENT}/{_PROMPT_NAME}@{prompt_version}"
        # Annotate the active ``planner.plan`` span with the same facts we persist, so a
        # trace shows model/tokens/cost without joining back to Postgres.
        add_llm_attributes(
            current_span(),
            model=self._model,
            prompt_version=full_version,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=float(cost) if cost is not None else 0.0,
        )
        await self._recorder(
            session_id=session_id,
            agent="planner",
            model=self._model,
            prompt_version=full_version,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            tool_calls=None,
        )


def _extract_text(response: Message) -> str:
    for block in response.content:
        if isinstance(block, TextBlock):
            return block.text
    raise PlannerOutputError("model response contained no text block")


def _strip_fences(text: str) -> str:
    """Drop a leading ```json / ``` fence and trailing ``` if the model wrapped its JSON
    despite the prompt (R6) — a common, cheap-to-tolerate deviation."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    body = stripped[3:]
    if body[:4].lower() == "json":
        body = body[4:]
    return body.rsplit("```", 1)[0].strip()


def _parse(text: str) -> Plan:
    try:
        payload = cast(object, json.loads(_strip_fences(text)))
    except json.JSONDecodeError as exc:
        raise PlannerOutputError(f"planner output was not JSON: {exc}") from exc
    try:
        return Plan.model_validate(payload)
    except ValidationError as exc:
        raise PlannerOutputError(f"planner output did not match Plan schema: {exc}") from exc
