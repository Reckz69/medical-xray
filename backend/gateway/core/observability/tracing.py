"""Tracing facade — a single surface for spans and span context.

Business code wraps work in spans without importing OpenTelemetry::

    with tracer.span("storage.upload", attributes={"key": key}):
        stored = await storage.upload(...)

When tracing is disabled, ``span()`` is ``contextlib.nullcontext()`` — a no-op
context manager that works in both sync and async code, so there is no ``if
enabled`` branching anywhere.

The OpenTelemetry SDK, OTLP exporter, and the collector/Jaeger wiring land in
Sprint 4B Phase 3; until then the facade is a no-op. ``get_current_span_context``
feeds ``trace_id`` / ``span_id`` into the structured logs.
"""

from __future__ import annotations

import contextlib
from typing import Any


class TracerFacade:
    """Lazily configured span factory; no-op context manager when disabled."""

    def __init__(self) -> None:
        self._enabled = False

    def configure(self, *, enabled: bool) -> None:
        self._enabled = enabled

    def span(
        self,
        name: str,
        *,
        attributes: dict[str, Any] | None = None,
    ) -> contextlib.AbstractContextManager[None]:
        """Context manager for a span. No-op when tracing is disabled."""
        return contextlib.nullcontext()

    def get_current_span_context(self) -> tuple[str | None, str | None]:
        """Return the active span's (trace_id, span_id), or (None, None)."""
        return (None, None)


tracer = TracerFacade()
