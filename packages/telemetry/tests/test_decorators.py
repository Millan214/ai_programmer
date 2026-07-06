"""``@traced`` span behavior: wrapping, task_id propagation, arg capture, exceptions."""

import uuid

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
from platform_telemetry.context import set_task_context
from platform_telemetry.decorators import add_llm_attributes, current_span, traced


@pytest.mark.asyncio
async def test_traced_wraps_function_and_creates_span(spans: InMemorySpanExporter) -> None:
    @traced("do.work")
    async def work(x: int) -> int:
        return x * 2

    assert await work(21) == 42

    finished = spans.get_finished_spans()
    assert [s.name for s in finished] == ["do.work"]


@pytest.mark.asyncio
async def test_task_id_from_context_lands_on_span(spans: InMemorySpanExporter) -> None:
    task_id = uuid.uuid4()
    set_task_context(task_id)

    @traced("phase.plan")
    async def node() -> None:
        return None

    await node()

    span = spans.get_finished_spans()[0]
    assert span.attributes is not None
    assert span.attributes["task_id"] == str(task_id)


@pytest.mark.asyncio
async def test_explicit_task_id_kwarg_wins(spans: InMemorySpanExporter) -> None:
    set_task_context(uuid.uuid4())
    explicit = uuid.uuid4()

    @traced("op")
    async def op(*, task_id: uuid.UUID) -> None:
        return None

    await op(task_id=explicit)

    span = spans.get_finished_spans()[0]
    assert span.attributes is not None
    assert span.attributes["task_id"] == str(explicit)


@pytest.mark.asyncio
async def test_capture_args_records_scalars_only(spans: InMemorySpanExporter) -> None:
    @traced("op", capture_args=True)
    async def op(*, name: str, payload: dict[str, int]) -> None:
        return None

    await op(name="hello", payload={"a": 1})

    span = spans.get_finished_spans()[0]
    assert span.attributes is not None
    assert span.attributes["arg.name"] == "hello"
    assert "arg.payload" not in span.attributes  # dicts aren't captured


@pytest.mark.asyncio
async def test_exception_is_recorded_and_reraised(spans: InMemorySpanExporter) -> None:
    @traced("op")
    async def boom() -> None:
        raise ValueError("kaboom")

    with pytest.raises(ValueError, match="kaboom"):
        await boom()

    span = spans.get_finished_spans()[0]
    assert span.status.status_code == StatusCode.ERROR
    assert any(event.name == "exception" for event in span.events)


@pytest.mark.asyncio
async def test_add_llm_attributes(spans: InMemorySpanExporter) -> None:
    @traced("planner.plan")
    async def plan() -> None:
        add_llm_attributes(
            current_span(),
            model="claude-opus-4-8",
            prompt_version="planner/plan@v1",
            input_tokens=120,
            output_tokens=240,
            cost_usd=0.0198,
        )

    await plan()

    span = spans.get_finished_spans()[0]
    assert span.attributes is not None
    assert span.attributes["llm.model"] == "claude-opus-4-8"
    assert span.attributes["llm.input_tokens"] == 120
    assert span.attributes["llm.cost_usd"] == pytest.approx(0.0198)
