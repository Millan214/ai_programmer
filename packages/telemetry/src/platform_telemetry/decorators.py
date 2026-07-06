"""``@traced`` for async functions, plus the LLM-attribute helper.

``@traced`` opens a span, stamps ``task_id`` (from an explicit kwarg if present, else the
contextvar set at run start), optionally captures scalar args, and records+re-raises on
exception. With no configured provider the tracer is OTel's no-op, so decorated functions
run unchanged in unit tests — instrumentation is free to add everywhere.
"""

import functools
import inspect
import uuid
from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar

from opentelemetry import trace
from opentelemetry.trace import Span, StatusCode

from platform_telemetry.context import get_task_context

_P = ParamSpec("_P")
_R = TypeVar("_R")

_TRACER_NAME = "platform"
# Args worth putting on a span; everything else (dicts, models, handles) is noise or PII.
_CAPTURABLE = (str, int, float, bool)


def traced(
    span_name: str, *, capture_args: bool = False
) -> Callable[[Callable[_P, Awaitable[_R]]], Callable[_P, Awaitable[_R]]]:
    def decorator(func: Callable[_P, Awaitable[_R]]) -> Callable[_P, Awaitable[_R]]:
        signature = inspect.signature(func)

        @functools.wraps(func)
        async def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            # Bind so positional and keyword args are treated alike (``retrieve(q, repo,
            # mode)`` is called positionally; ``plan(task_id=...)`` by keyword).
            arguments = dict(signature.bind_partial(*args, **kwargs).arguments)
            tracer = trace.get_tracer(_TRACER_NAME)
            with tracer.start_as_current_span(span_name) as span:
                _stamp_task_id(span, arguments)
                if capture_args:
                    _capture_args(span, arguments)
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:
                    span.record_exception(exc)
                    span.set_status(StatusCode.ERROR, str(exc))
                    raise

        return wrapper

    return decorator


def _stamp_task_id(span: Span, kwargs: dict[str, object]) -> None:
    task_id = kwargs.get("task_id")
    if not isinstance(task_id, uuid.UUID):
        task_id = get_task_context()
    if task_id is not None:
        span.set_attribute("task_id", str(task_id))


def _capture_args(span: Span, kwargs: dict[str, object]) -> None:
    for key, value in kwargs.items():
        if key != "task_id" and isinstance(value, _CAPTURABLE):
            span.set_attribute(f"arg.{key}", value)


def add_llm_attributes(
    span: Span,
    *,
    model: str,
    prompt_version: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
) -> None:
    """Annotate an LLM-call span with the same facts persisted on ``agent_turn``."""
    span.set_attribute("llm.model", model)
    span.set_attribute("llm.prompt_version", prompt_version)
    span.set_attribute("llm.input_tokens", input_tokens)
    span.set_attribute("llm.output_tokens", output_tokens)
    span.set_attribute("llm.cost_usd", cost_usd)


def current_span() -> Span:
    """The active span (a no-op span if tracing isn't configured) — for attaching
    attributes from a helper that isn't itself the decorated function."""
    return trace.get_current_span()
