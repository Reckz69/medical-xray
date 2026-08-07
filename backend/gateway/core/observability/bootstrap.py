"""Observability bootstrap — wires logging, metrics, and tracing together.

Called once from each process entry point (``gateway.main``, ``worker.main``,
``scheduler.main``) with that process's name and configuration. Business code
never calls this directly.
"""

from __future__ import annotations

from gateway.core.config import settings
from gateway.core.observability.logging import configure_logging, set_correlation
from gateway.core.observability.metrics import metrics
from gateway.core.observability.tracing import tracer


def init_observability(
    *,
    service: str,
    log_level: str = "INFO",
    otel_enabled: bool = False,
    metrics_enabled: bool = False,
) -> None:
    """Configure observability for a service process.

    ``service`` is stamped on every log record. Disabled components become
    no-ops (see the facade contracts in ``metrics.py`` / ``tracing.py``).
    """
    configure_logging(log_level)
    tracer.configure(
        enabled=otel_enabled,
        service=service,
        exporter_name=settings.otel_exporter,
        endpoint=settings.otel_endpoint,
    )
    metrics.configure(enabled=metrics_enabled)
    set_correlation(service=service)
