"""Metrics facade — a single surface for Prometheus instruments.

Business code records metrics against the ``metrics`` facade using attribute
access, e.g.::

    metrics.scan_upload_seconds.observe(seconds)
    metrics.worker_job_failures_total.inc()

Instruments are declared in :data:`_INSTRUMENT_SPECS` (name -> kind/help/labels)
and materialised lazily on first access against a process-local registry, so
each process only creates the instruments it actually touches. When metrics
are disabled the facade returns no-op instruments, so call sites need no ``if
enabled`` branching and observability remains fully removable.

The process-local ``CollectorRegistry`` keeps one process's instruments out of
another's scrape (the gateway serves ``/metrics`` from the FastAPI app; worker
and scheduler run a Prometheus HTTP server on ``metrics_port``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from prometheus_client import (
    PROCESS_COLLECTOR,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    start_http_server,
)


class NoopInstrument:
    """Drop-in stand-in for a Prometheus instrument that records nothing."""

    def inc(self, *args: Any, **kwargs: Any) -> None:
        return None

    def observe(self, *args: Any, **kwargs: Any) -> None:
        return None

    def set(self, *args: Any, **kwargs: Any) -> None:
        return None

    def labels(self, *args: Any, **kwargs: Any) -> NoopInstrument:
        return self


@dataclass(frozen=True)
class InstrumentSpec:
    """Declaration of one Prometheus instrument behind the facade."""

    kind: str  # "counter" | "gauge" | "histogram"
    help: str
    labelnames: tuple[str, ...] = ()


#: Every metric the business code may record, keyed by the facade attribute.
#: Adding a metric here is the one place instrument metadata lives.
_INSTRUMENT_SPECS: dict[str, InstrumentSpec] = {
    # ── Gateway ──────────────────────────────────────────────────────────────
    "http_requests_total": InstrumentSpec(
        "counter",
        "HTTP requests served by the gateway",
        ("method", "status"),
    ),
    "http_request_duration_seconds": InstrumentSpec(
        "histogram",
        "Gateway request latency",
        ("method", "status"),
    ),
    "scan_upload_seconds": InstrumentSpec(
        "histogram",
        "Time to persist an uploaded scan (object storage + rows)",
    ),
    # ── Worker ───────────────────────────────────────────────────────────────
    "worker_job_duration_seconds": InstrumentSpec(
        "histogram",
        "Wall-clock time for one inference.run job (message in -> job done)",
    ),
    "worker_inference_seconds": InstrumentSpec(
        "histogram",
        "Model inference time (orchestrator inference_ms)",
    ),
    "worker_processing_seconds": InstrumentSpec(
        "histogram",
        "Full pipeline processing time (orchestrator total_ms)",
    ),
    "worker_job_failures_total": InstrumentSpec(
        "counter",
        "Jobs the worker failed terminally (all attempts exhausted)",
    ),
    # ── Scheduler ────────────────────────────────────────────────────────────
    "scheduler_jobs_republished_total": InstrumentSpec(
        "counter",
        "Retry commands republished by the scheduler (due + unconfirmed)",
    ),
    "scheduler_cleanup_duration_seconds": InstrumentSpec(
        "gauge",
        "Wall-clock time of the last cleanup pass",
    ),
    "scheduler_cleanup_failures_total": InstrumentSpec(
        "counter",
        "Cleanup passes or object deletes that failed",
    ),
    "scheduler_cleanup_skipped_total": InstrumentSpec(
        "counter",
        "Cleanup runs skipped (lock held or lock error)",
    ),
    "jobs_by_status": InstrumentSpec(
        "gauge",
        "Current jobs grouped by status (per-cycle GROUP BY)",
        ("status",),
    ),
}


class MetricsFacade:
    """Lazily materialises Prometheus instruments; no-ops when disabled."""

    #: Prometheus text exposition media type served by ``render()``.
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"

    def __init__(self) -> None:
        self._enabled = False
        self._instruments: dict[str, Any] = {}
        self._registry = CollectorRegistry()

    def configure(self, *, enabled: bool) -> None:
        """Enable or disable real instruments for this process.

        Re-configuring (tests) replaces the registry and drops any cached
        instruments, so each process/enable has a clean scrape surface.
        """
        self._enabled = enabled
        self._instruments = {}
        self._registry = CollectorRegistry()
        if enabled:
            # CPU/mem usage for the process (ADR-010 requirement map).
            self._registry.register(PROCESS_COLLECTOR)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        instrument = self._instruments.get(name)
        if instrument is None:
            instrument = self._build(name)
            self._instruments[name] = instrument
        return instrument

    def _build(self, name: str) -> Any:
        if not self._enabled:
            return NoopInstrument()
        spec = _INSTRUMENT_SPECS.get(name)
        if spec is None:
            return NoopInstrument()
        if spec.kind == "counter":
            return Counter(name, spec.help, list(spec.labelnames), registry=self._registry)
        if spec.kind == "gauge":
            return Gauge(name, spec.help, list(spec.labelnames), registry=self._registry)
        if spec.kind == "histogram":
            return Histogram(name, spec.help, list(spec.labelnames), registry=self._registry)
        return NoopInstrument()

    # ── Exposure ─────────────────────────────────────────────────────────────
    def render(self) -> bytes:
        """Prometheus text exposition of this process's metrics."""
        return generate_latest(self._registry)

    def start_server(self, port: int) -> None:
        """Run a Prometheus HTTP scrape endpoint in a background thread.

        Used by the worker and scheduler (ADR-010); the gateway serves
        ``/metrics`` from the FastAPI app instead.
        """
        start_http_server(port, registry=self._registry)


#: The one facade instance shared by every service process.
metrics = MetricsFacade()
