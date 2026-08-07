"""Tracing facade — a single surface for spans and span context.

Business code wraps work in spans without importing OpenTelemetry::

    with tracer.span("storage.upload", attributes={"key": key}):
        stored = await storage.upload(...)

and continues a remote trace (gateway request -> RabbitMQ -> worker) with::

    with tracer.span_from_traceparent(headers.get("traceparent"), name="worker.inference.run"):
        ...

When tracing is disabled both are ``contextlib.nullcontext()`` — no-op context
managers that work in sync and async code, so there is no ``if enabled``
branching anywhere.

When enabled, ``configure`` builds an SDK ``TracerProvider`` with an OTLP/HTTP
exporter (the collector, or a trace backend directly — ADR-010 keeps that a
config-only swap) plus a ``BatchSpanProcessor``. Tests inject an exporter and
the facade uses a ``SimpleSpanProcessor`` so finished spans are available
deterministically. ``get_current_span_context`` feeds ``trace_id``/``span_id``
into the structured logs, and ``get_current_traceparent`` produces the W3C
``traceparent`` header injected into RabbitMQ messages (``queue.py``).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
    SpanExporter,
)
from opentelemetry.trace import (
    format_span_id,
    format_trace_id,
    get_current_span,
)
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator


class TracerFacade:
    """Lazily built span factory; no-op context managers when disabled."""

    def __init__(self) -> None:
        self._enabled = False
        self._tracer: Any = None
        self._provider: TracerProvider | None = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    def configure(
        self,
        *,
        enabled: bool,
        service: str = "",
        exporter: SpanExporter | None = None,
        exporter_name: str = "otlp-http",
        endpoint: str = "",
    ) -> None:
        """Build or tear down the SDK wiring for this process.

        ``exporter`` is normally ``None`` (built from ``exporter_name`` /
        ``endpoint``); tests inject an ``InMemorySpanExporter`` so the facade
        uses a synchronous ``SimpleSpanProcessor`` and finished spans are
        available immediately. Re-configuring shuts down prior wiring first.
        """
        self.shutdown()
        self._enabled = enabled
        if not enabled:
            return
        provider = TracerProvider(
            resource=Resource.create({SERVICE_NAME: service or "denoise-x"})
        )
        if exporter is not None:
            provider.add_span_processor(SimpleSpanProcessor(exporter))
        else:
            provider.add_span_processor(
                BatchSpanProcessor(self._default_exporter(exporter_name, endpoint))
            )
        self._provider = provider
        self._tracer = provider.get_tracer("denoise-x")

    def _default_exporter(self, exporter_name: str, endpoint: str) -> SpanExporter:
        if exporter_name == "console":
            return ConsoleSpanExporter()
        return OTLPSpanExporter(endpoint=endpoint or None)

    @contextmanager
    def span(
        self,
        name: str,
        *,
        attributes: dict[str, Any] | None = None,
    ) -> Iterator[None]:
        """Context manager for a span. No-op when tracing is disabled."""
        if not self._enabled or self._tracer is None:
            yield
            return
        with self._tracer.start_as_current_span(name, attributes=attributes):
            yield

    @contextmanager
    def span_from_traceparent(
        self,
        traceparent: str | None,
        name: str,
        *,
        attributes: dict[str, Any] | None = None,
    ) -> Iterator[None]:
        """Start a span that continues the remote trace in ``traceparent``.

        A missing or malformed traceparent starts a fresh root span. No-op when
        tracing is disabled.
        """
        if not self._enabled or self._tracer is None:
            yield
            return
        parent_context = None
        if traceparent:
            parent_context = TraceContextTextMapPropagator().extract(
                {"traceparent": traceparent}
            )
        with self._tracer.start_as_current_span(
            name, context=parent_context, attributes=attributes
        ):
            yield

    def get_current_span_context(self) -> tuple[str | None, str | None]:
        """Return the active span's (trace_id, span_id), or (None, None)."""
        if not self._enabled:
            return (None, None)
        span_context = get_current_span().get_span_context()
        if not span_context.is_valid:
            return (None, None)
        return (format_trace_id(span_context.trace_id), format_span_id(span_context.span_id))

    def get_current_traceparent(self) -> str | None:
        """W3C ``traceparent`` for the active span, or ``None`` when disabled."""
        if not self._enabled:
            return None
        trace_id, _ = self.get_current_span_context()
        if trace_id is None:
            return None
        carrier: dict[str, str] = {}
        TraceContextTextMapPropagator().inject(carrier)
        return carrier.get("traceparent")

    def shutdown(self) -> None:
        """Flush and stop span export (call at process shutdown)."""
        if self._provider is not None:
            try:
                self._provider.shutdown()
            except Exception:  # noqa: BLE001, S110 — shutdown must never raise
                pass
        self._provider = None
        self._tracer = None


tracer = TracerFacade()
