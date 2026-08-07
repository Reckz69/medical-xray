"""Metrics facade — a single surface for Prometheus instruments.

Business code records metrics against the ``metrics`` facade using attribute
access, e.g.::

    metrics.scan_upload_seconds.observe(seconds)
    metrics.worker_job_failures_total.inc()

Instruments are materialised lazily on first access (each process only creates
the instruments it actually touches). When metrics are disabled the facade
returns no-op instruments, so call sites need no ``if enabled`` branching.

The real Prometheus registry + ``/metrics`` HTTP exposure are wired up in
``bootstrap.py`` and the per-service entry points (Sprint 4B Phase 2); until
then the facade is a no-op and observability remains removable.
"""

from __future__ import annotations

from typing import Any


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


class MetricsFacade:
    """Lazily materialises instruments; no-op instruments when disabled."""

    def __init__(self) -> None:
        self._enabled = False
        self._instruments: dict[str, Any] = {}

    def configure(self, *, enabled: bool) -> None:
        self._enabled = enabled

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        instrument = self._instruments.get(name)
        if instrument is None:
            instrument = self._build(name)
            self._instruments[name] = instrument
        return instrument

    def _build(self, name: str) -> Any:
        # Phase 2 wires real prometheus_client instruments here keyed by the
        # (name -> kind/help/labels) map. Until then, everything is a no-op.
        return NoopInstrument()


metrics = MetricsFacade()
