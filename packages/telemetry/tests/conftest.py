"""Shared tracing fixtures: a global in-memory provider set once for the session (OTel's
``set_tracer_provider`` is set-once), with the exporter cleared before each test so
``@traced`` spans land somewhere assertable.
"""

from collections.abc import Iterator

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from platform_telemetry.setup import configure

_EXPORTER = InMemorySpanExporter()


@pytest.fixture(scope="session", autouse=True)
def _global_tracing() -> None:
    # One global provider for the whole session; the decorator reads it via get_tracer.
    configure("telemetry-tests", exporter=_EXPORTER, instrument=False)


@pytest.fixture
def spans() -> Iterator[InMemorySpanExporter]:
    _EXPORTER.clear()
    yield _EXPORTER
    _EXPORTER.clear()
