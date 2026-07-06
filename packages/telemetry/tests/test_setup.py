"""``configure`` builds a working provider and stays offline-safe."""

import pytest
from opentelemetry.sdk.resources import SERVICE_NAME
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from platform_telemetry.setup import _default_exporter, configure


def test_configure_returns_provider_that_emits_spans() -> None:
    exporter = InMemorySpanExporter()
    provider = configure("svc-a", exporter=exporter, set_global=False, instrument=False)

    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("unit"):
        pass
    provider.force_flush()

    assert [s.name for s in exporter.get_finished_spans()] == ["unit"]


def test_resource_carries_service_name() -> None:
    exporter = InMemorySpanExporter()
    provider = configure("svc-b", exporter=exporter, set_global=False, instrument=False)

    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("s"):
        pass
    provider.force_flush()

    span = exporter.get_finished_spans()[0]
    assert span.resource.attributes[SERVICE_NAME] == "svc-b"


def test_no_exporter_when_endpoint_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    # No OTLP endpoint → no default exporter → nothing tries to reach a collector offline.
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    assert _default_exporter() is None


def test_configure_offline_is_harmless(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    provider = configure("svc-c", set_global=False, instrument=False)

    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("s"):
        pass
    provider.force_flush()  # no exporter attached; must not raise


def test_endpoint_present_builds_otlp_exporter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    exporter = _default_exporter()
    assert exporter is not None
    assert exporter.__class__.__name__ == "OTLPSpanExporter"
