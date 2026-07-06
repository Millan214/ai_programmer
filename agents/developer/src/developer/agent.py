"""DeveloperAgent — the ReAct loop that edits code in the sandbox (card 08).

One tool call per model turn: prompt with the plan and history, execute the tool the
model picked, feed the observation back, repeat. Every iteration persists an
``agent_turn`` row via the injected ``TurnRecorder``. The loop exits on the first of:

- **passed** — a verifier run after an edit came back green (the Verifier is the only
  authority; the model's own claim of success is not an exit condition, ADR-0006).
- **budget_exceeded** — cumulative tokens crossed ``MAX_DEVELOPER_TOKENS_PER_TASK``.
- **stuck** — the same tool with the same arguments three times in a row.
- **max_iterations** — ``DEVELOPER_MAX_ITERATIONS`` (default 15) turns without any of
  the above.

Non-goals (per card 08): no supervisor, no context compression (full history every
turn — the budget cap is the backstop), no concurrency, no prompt caching.
"""

import json
import os
import uuid
from typing import cast

from anthropic import AsyncAnthropic
from anthropic.types import (
    Message,
    MessageParam,
    TextBlock,
    TextBlockParam,
    ToolParam,
    ToolResultBlockParam,
    ToolUseBlock,
    ToolUseBlockParam,
)
from orchestrator.protocols import PlanDict, TurnRecorder
from platform_shared.pricing import compute_cost
from prompts.registry import PromptRef, active_version, render
from sandbox.models import SandboxHandle
from verifier.models import VerifierResult

from developer.models import BuildResult, BuildStatus, skipped_verifier_result
from developer.tools import DeveloperToolsProtocol, ToolExecutionError

_MODEL_ENV = "DEVELOPER_MODEL"
# Sonnet: the loop makes up to N calls per task with full history each turn (no prompt
# caching in Phase 0), so per-call cost multiplies — the balanced tier fits tool-use
# iteration; Opus-class models stay on the one-shot Planner.
_DEFAULT_MODEL = "claude-sonnet-4-6"
_MAX_ITERATIONS_ENV = "DEVELOPER_MAX_ITERATIONS"
_DEFAULT_MAX_ITERATIONS = 15
_TOKEN_BUDGET_ENV = "MAX_DEVELOPER_TOKENS_PER_TASK"
_DEFAULT_TOKEN_BUDGET = 200_000
_MAX_RESPONSE_TOKENS = 8192
_STUCK_REPEATS = 3
_PROMPT_AGENT = "developer"
_PROMPT_NAME = "build"

_TOOLS: list[ToolParam] = [
    {
        "name": "retrieve",
        "description": (
            "Ask the Context Provider for code context. mode='symbol' finds a specific "
            "definition or reference; mode='explore' maps a neighborhood of related code."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "mode": {"type": "string", "enum": ["symbol", "explore"]},
            },
            "required": ["query", "mode"],
        },
    },
    {
        "name": "read_file",
        "description": "Read one file from the sandbox by repo-relative path.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "edit_file",
        "description": (
            "Replace the full content of one file (created if missing). The Verifier "
            "runs automatically after every edit and its report is returned to you."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
    },
    {
        "name": "run_verifier",
        "description": "Run build, tests, typecheck, and lint against the current worktree.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw else default


def _is_green(facts: VerifierResult) -> bool:
    """Green = nothing failed and the build actually ran. ``skip`` elsewhere is
    non-blocking (e.g. a repo with zero tests), matching the Verifier's semantics."""
    statuses = (facts.build.status, facts.typecheck.status, facts.tests.status, facts.lint.status)
    return facts.build.status == "pass" and all(s in ("pass", "skip") for s in statuses)


def _summarize_facts(facts: VerifierResult) -> str:
    lines = [
        "verifier report: "
        f"build={facts.build.status} typecheck={facts.typecheck.status} "
        f"tests={facts.tests.status} ({facts.tests.passed}/{facts.tests.total} passed) "
        f"lint={facts.lint.status}"
    ]
    if facts.build.error:
        lines.append(f"build error (tail): {facts.build.error[-1500:]}")
    for error in facts.typecheck.errors[:5]:
        lines.append(
            f"typecheck: {error.file}({error.line},{error.column}) {error.code} {error.message}"
        )
    for failure in facts.tests.failures[:5]:
        lines.append(f"test failure: {failure.name}: {failure.message[:500]}")
    for issue in facts.lint.issues[:5]:
        lines.append(f"lint {issue.severity}: {issue.file}: {issue.message}")
    return "\n".join(lines)


class DeveloperAgent:
    """Concrete Developer. Adapt via ``DeveloperProtocolAdapter`` to satisfy the protocol."""

    def __init__(
        self,
        *,
        recorder: TurnRecorder,
        tools: DeveloperToolsProtocol,
        client: AsyncAnthropic | None = None,
        model: str | None = None,
        max_iterations: int | None = None,
        token_budget: int | None = None,
    ) -> None:
        self._recorder = recorder
        self._tools = tools
        self._client = client if client is not None else AsyncAnthropic()
        self._model = model or os.environ.get(_MODEL_ENV) or _DEFAULT_MODEL
        self._max_iterations = (
            max_iterations
            if max_iterations is not None
            else _int_env(_MAX_ITERATIONS_ENV, _DEFAULT_MAX_ITERATIONS)
        )
        self._token_budget = (
            token_budget
            if token_budget is not None
            else _int_env(_TOKEN_BUDGET_ENV, _DEFAULT_TOKEN_BUDGET)
        )

    async def build(
        self, plan: PlanDict, sandbox: SandboxHandle, session_id: uuid.UUID
    ) -> BuildResult:
        version = active_version(_PROMPT_AGENT, _PROMPT_NAME)
        plan_json = json.dumps(plan, indent=2, default=str)
        system = render(
            PromptRef(agent=_PROMPT_AGENT, name=_PROMPT_NAME, version=version),
            plan=plan_json,
            repo_map=_repo_map(plan),
        )
        messages: list[MessageParam] = [
            {"role": "user", "content": "Begin. Work the plan's subtasks in order."}
        ]

        tokens_spent = 0
        last_facts: VerifierResult | None = None
        last_signature: tuple[str, str] | None = None
        repeat_count = 0

        for _ in range(self._max_iterations):
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=_MAX_RESPONSE_TOKENS,
                system=system,
                messages=messages,
                tools=_TOOLS,
            )
            tool_uses = [b for b in response.content if isinstance(b, ToolUseBlock)]
            await self._record_turn(session_id, version, response, tool_uses)

            tokens_spent += response.usage.input_tokens + response.usage.output_tokens
            if tokens_spent > self._token_budget:
                return await self._finish("budget_exceeded", sandbox, last_facts)

            messages.append({"role": "assistant", "content": _to_param_blocks(response)})

            if not tool_uses:
                # The model stopped calling tools without a green verifier run — its own
                # word is not a fact (ADR-0006). Nudge; the iteration cap bounds this.
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "You stopped without a green verifier run. Continue working "
                            "the plan; use run_verifier to confirm before finishing."
                        ),
                    }
                )
                continue

            results: list[ToolResultBlockParam] = []
            for block in tool_uses:
                signature = (block.name, json.dumps(block.input, sort_keys=True, default=str))
                repeat_count = repeat_count + 1 if signature == last_signature else 1
                last_signature = signature
                if repeat_count >= _STUCK_REPEATS:
                    return await self._finish("stuck", sandbox, last_facts)

                output, facts, is_error = await self._dispatch(block, sandbox)
                if facts is not None:
                    last_facts = facts
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": output,
                        "is_error": is_error,
                    }
                )
                if facts is not None and _is_green(facts):
                    return await self._finish("passed", sandbox, last_facts)
            messages.append({"role": "user", "content": results})

        return await self._finish("max_iterations", sandbox, last_facts)

    async def _dispatch(
        self, block: ToolUseBlock, sandbox: SandboxHandle
    ) -> tuple[str, VerifierResult | None, bool]:
        """Execute one tool call; returns (observation, verifier facts if any, is_error)."""
        args = block.input
        try:
            if block.name == "retrieve":
                query, mode = args.get("query"), args.get("mode")
                if not isinstance(query, str) or not isinstance(mode, str):
                    return ("retrieve needs string 'query' and 'mode'", None, True)
                return (await self._tools.retrieve(query, mode), None, False)
            if block.name == "read_file":
                path = args.get("path")
                if not isinstance(path, str):
                    return ("read_file needs a string 'path'", None, True)
                return (await self._tools.read_file(path, sandbox), None, False)
            if block.name == "edit_file":
                path, content = args.get("path"), args.get("content")
                if not isinstance(path, str) or not isinstance(content, str):
                    return ("edit_file needs string 'path' and 'content'", None, True)
                await self._tools.edit_file(path, content, sandbox)
                facts = await self._tools.run_verifier(sandbox)
                return (f"File written.\n{_summarize_facts(facts)}", facts, False)
            if block.name == "run_verifier":
                facts = await self._tools.run_verifier(sandbox)
                return (_summarize_facts(facts), facts, False)
            return (f"unknown tool: {block.name}", None, True)
        except ToolExecutionError as exc:
            return (str(exc), None, True)

    async def _finish(
        self, status: BuildStatus, sandbox: SandboxHandle, last_facts: VerifierResult | None
    ) -> BuildResult:
        diff = await self._tools.get_diff(sandbox)
        return BuildResult(
            status=status,
            diff=diff,
            verifier_facts=last_facts if last_facts is not None else skipped_verifier_result(),
        )

    async def _record_turn(
        self,
        session_id: uuid.UUID,
        prompt_version: str,
        response: Message,
        tool_uses: list[ToolUseBlock],
    ) -> None:
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        await self._recorder(
            session_id=session_id,
            agent="developer",
            model=self._model,
            prompt_version=f"{_PROMPT_AGENT}/{_PROMPT_NAME}@{prompt_version}",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=compute_cost(self._model, input_tokens, output_tokens),
            tool_calls={"calls": [{"tool": b.name, "input": b.input} for b in tool_uses]},
        )


def _to_param_blocks(response: Message) -> list[TextBlockParam | ToolUseBlockParam]:
    """Re-encode response blocks as request params so history round-trips typed."""
    blocks: list[TextBlockParam | ToolUseBlockParam] = []
    for block in response.content:
        if isinstance(block, TextBlock):
            blocks.append({"type": "text", "text": block.text})
        elif isinstance(block, ToolUseBlock):
            blocks.append(
                {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
            )
    return blocks


def _repo_map(plan: PlanDict) -> str:
    """Phase 0 has no repo indexer output to inline; the plan's file hints stand in."""
    files = plan.get("estimated_files")
    if isinstance(files, list) and files:
        hints = "\n".join(f"- {f}" for f in cast("list[object]", files))
        return f"Planner file hints (not verified — confirm with retrieve):\n{hints}"
    return "(none available — use retrieve to map the repository)"
