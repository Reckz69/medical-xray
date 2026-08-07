"""Observability facade (Sprint 4B, ADR-010).

One package owns logging, metrics, and tracing. Business code imports exactly
one surface:

    from gateway.core.observability import tracer, metrics, log_context

and never reads configuration or touches Prometheus / OpenTelemetry directly.
If Prometheus, OpenTelemetry, or the trace backend are replaced, only this
package changes (ADR-010 "collector as abstraction").

Every component honours a disabled-mode contract: when ``init_observability``
is called with ``otel_enabled=False`` / ``metrics_enabled=False`` the facade
swaps in no-op implementations, so call sites need no ``if enabled``
branching — observability is fully removable.
"""

from __future__ import annotations

from gateway.core.observability.bootstrap import init_observability
from gateway.core.observability.logging import configure_logging, log_context
from gateway.core.observability.metrics import metrics
from gateway.core.observability.tracing import tracer

__all__ = [
    "configure_logging",
    "init_observability",
    "log_context",
    "metrics",
    "tracer",
]
