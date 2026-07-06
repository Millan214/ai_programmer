"""Tracer-provider setup and FastAPI/httpx/SQLAlchemy auto-instrumentation.

``configure`` is called once at service startup. Two properties matter for this codebase:

- **Offline-safe.** With ``OTEL_EXPORTER_OTLP_ENDPOINT`` unset (CI, ``make test``, a laptop
  with no collector) it installs a provider with *no* exporter — spans are created and then
  dropped, so nothing tries to reach a collector and nothing is logged. Instrumentation and
  ``@traced`` stay live but inert.
- **Testable without the global.** ``configure`` returns the provider and takes an optional
  ``exporter`` (tests pass an ``InMemorySpanExporter``) and ``set_global`` — so a test can
  build a provider, emit spans, and assert on them without touching global state or fighting
  OTel's set-once ``set_tracer_provider``.

Auto-instrumentation is best-effort: each instrumentor is guarded so a missing or
version-incompatible one degrades to "no spans from that layer" rather than crashing
startup. Note the DB layer uses **psycopg**, not asyncpg (see ``platform_db.session``), so
the card's asyncpg instrumentation doesn't apply — SQLAlchemy instrumentation covers DB
spans at the engine level instead.
"""

import contextlib
import os
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExporter,
)

_OTLP_ENDPOINT_ENV = "OTEL_EXPORTER_OTLP_ENDPOINT"

_global_configured = False
_instrumented = False


def _default_exporter() -> SpanExporter | None:
    if not os.environ.get(_OTLP_ENDPOINT_ENV):
        return None
    # Imported lazily: the OTLP exporter pulls in grpc, which we don't want to import in
    # offline runs that will never export.
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

    return OTLPSpanExporter()


def configure(
    service_name: str,
    *,
    exporter: SpanExporter | None = None,
    set_global: bool = True,
    instrument: bool = True,
) -> TracerProvider:
    """Build a tracer provider for ``service_name`` and (by default) install it globally.

    ``exporter`` overrides the endpoint-derived default (tests inject in-memory). An
    injected exporter uses a synchronous processor so spans are visible immediately;
    the production OTLP path batches.
    """
    global _global_configured
    resource = Resource.create({SERVICE_NAME: service_name})
    provider = TracerProvider(resource=resource)

    span_exporter = exporter if exporter is not None else _default_exporter()
    if span_exporter is not None:
        processor = (
            SimpleSpanProcessor(span_exporter)
            if exporter is not None
            else BatchSpanProcessor(span_exporter)
        )
        provider.add_span_processor(processor)

    if set_global and not _global_configured:
        trace.set_tracer_provider(provider)
        _global_configured = True

    if instrument:
        _instrument_once()

    return provider


def _instrument_once() -> None:
    global _instrumented
    if _instrumented:
        return
    _instrumented = True
    _safe_instrument_httpx()
    _safe_instrument_sqlalchemy()


def _safe_instrument_httpx() -> None:
    # Best-effort: a missing or version-incompatible instrumentor must not crash startup.
    with contextlib.suppress(Exception):
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()


def _safe_instrument_sqlalchemy() -> None:
    with contextlib.suppress(Exception):
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().instrument()


def lifespan_for(
    service_name: str,
) -> Callable[[object], AbstractAsyncContextManager[None]]:
    """A FastAPI ``lifespan`` that configures tracing + instruments the app on startup.

    Using lifespan (not import-time) means a bare ``TestClient(app)`` in unit tests never
    triggers it — instrumentation is a real-run concern, not a test-import side effect.
    """

    @asynccontextmanager
    async def lifespan(app: object) -> AsyncIterator[None]:
        configure(service_name)
        with contextlib.suppress(Exception):
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            FastAPIInstrumentor.instrument_app(app)  # type: ignore[arg-type]
        yield

    return lifespan
