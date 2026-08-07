"""Observability facade tests (Sprint 4B).

Phase 1 covers the disabled-mode contract and the correlation-context semantics:

* JsonFormatter emits valid JSON with structured fields.
* log_context sets fields for a block and restores the prior context on exit
  (nested merge + cleanup verified).
* set_correlation merges task-scoped fields (used for user_id after auth).
* The tracer/metrics facades are no-ops when disabled — no ``if enabled``
  branching, and both sync/async usage compile and run.
* TraceIDMiddleware stamps trace_id/request_id into the correlation context for
  the duration of a request and bridges a caller-supplied X-Request-ID.

Phase 2 covers the enabled-mode Prometheus surface:

* configure(enabled=True) materialises real instruments and render() exposes
  them in Prometheus text format; reconfigure resets the registry.
* Unknown instrument names stay no-ops even when enabled.
* MetricsMiddleware records http_requests_total / http_request_duration_seconds.
"""

from __future__ import annotations

import asyncio
import json
import logging

import httpx
import pytest

import gateway.core.observability.logging as logging_mod
from gateway.core.observability.logging import (
    JsonFormatter,
    get_correlation,
    log_context,
    set_correlation,
)
from gateway.core.observability.metrics import NoopInstrument, metrics
from gateway.core.observability.tracing import tracer
from gateway.core.otel import TraceIDMiddleware
from gateway.main import MetricsMiddleware

#: Every instrument the facade may materialise (Phase 2 spec set).
_ALL_INSTRUMENT_NAMES = (
    "http_requests_total",
    "http_request_duration_seconds",
    "scan_upload_seconds",
    "worker_job_duration_seconds",
    "worker_inference_seconds",
    "worker_processing_seconds",
    "worker_job_failures_total",
    "scheduler_jobs_republished_total",
    "scheduler_cleanup_duration_seconds",
    "scheduler_cleanup_failures_total",
    "scheduler_cleanup_skipped_total",
    "jobs_by_status",
)


@pytest.fixture(autouse=True)
def _isolated_correlation() -> None:
    """Reset the correlation ContextVar before each test.

    Tests share the session-scoped event loop, so correlation state would
    otherwise leak between tests (e.g. ``set_correlation`` persisting across
    test functions).
    """
    token = logging_mod._CORRELATION.set({})
    try:
        yield
    finally:
        logging_mod._CORRELATION.reset(token)


def _format_with_context(**fields: str) -> dict:
    """Format a record while `fields` are active in the correlation context."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="denoise.test",
        level=logging.INFO,
        pathname="/src/t.py",
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    with log_context(**fields):
        return json.loads(formatter.format(record))


def test_json_formatter_emits_valid_structured_record() -> None:
    entry = _format_with_context()
    assert entry["message"] == "hello world"
    assert entry["level"] == "INFO"
    assert entry["logger"] == "denoise.test"
    assert "timestamp" in entry
    # No correlation fields set -> none emitted.
    assert "trace_id" not in entry
    assert "scan_id" not in entry


def test_json_formatter_includes_correlation_fields() -> None:
    entry = _format_with_context(
        trace_id="t1",
        request_id="t1",
        scan_id="s1",
        job_id="j1",
        user_id="u1",
    )
    assert entry["trace_id"] == "t1"
    assert entry["request_id"] == "t1"
    assert entry["scan_id"] == "s1"
    assert entry["job_id"] == "j1"
    assert entry["user_id"] == "u1"


def test_log_context_merges_nested_and_cleans_up() -> None:
    assert get_correlation() == {}

    with log_context(scan_id="s1"):
        assert get_correlation()["scan_id"] == "s1"
        with log_context(job_id="j1"):
            # Inner scope sees outer fields too.
            assert get_correlation()["scan_id"] == "s1"
            assert get_correlation()["job_id"] == "j1"
        # Exiting inner restores exactly the outer context.
        assert get_correlation()["scan_id"] == "s1"
        assert "job_id" not in get_correlation()

    # Exiting outer clears everything (context cleanup verified).
    assert get_correlation() == {}


def test_log_context_ignores_empty_and_none_values() -> None:
    with log_context(trace_id="", scan_id=None):  # type: ignore[arg-type]
        assert get_correlation() == {}


def test_set_correlation_merges_and_persists() -> None:
    assert get_correlation() == {}
    set_correlation(user_id="u1")
    assert get_correlation()["user_id"] == "u1"
    set_correlation(scan_id="s1")
    assert get_correlation()["user_id"] == "u1"
    assert get_correlation()["scan_id"] == "s1"


def test_set_correlation_ignores_empty() -> None:
    set_correlation(scan_id="")
    assert get_correlation() == {}


def test_tracer_span_is_noop_when_disabled() -> None:
    tracer.configure(enabled=False)
    attributes = {"key": "value"}
    with tracer.span("storage.upload", attributes=attributes):
        pass  # no-op context manager must not raise
    assert tracer.get_current_span_context() == (None, None)


async def test_tracer_span_noop_in_async_context() -> None:
    with tracer.span("worker.consume"):
        await asyncio.sleep(0)


def test_metrics_facade_is_noop_when_disabled() -> None:
    metrics.configure(enabled=False)
    metrics.upload_latency_seconds.observe(1.5)
    metrics.http_requests_total.inc()
    metrics.jobs_in_flight.set(3)
    metrics.queue_depth.labels(queue="inference.worker").inc()
    # All no-op: no exception, and every materialised instrument is a no-op.
    for instrument in getattr(metrics, "_instruments", {}).values():
        assert isinstance(instrument, NoopInstrument)


def test_metrics_enabled_materializes_real_instruments() -> None:
    metrics.configure(enabled=True)
    try:
        counter = metrics.http_requests_total
        assert not isinstance(counter, NoopInstrument)
        counter.labels(method="GET", status="200").inc()

        metrics.jobs_by_status.labels(status="QUEUED").set(5)
        metrics.scan_upload_seconds.observe(1.25)

        body = metrics.render()
        assert b'http_requests_total{method="GET",status="200"} 1.0' in body
        assert b'jobs_by_status{status="QUEUED"} 5.0' in body
        assert b'scan_upload_seconds_sum' in body
        assert b"# HELP http_requests_total" in body
    finally:
        metrics.configure(enabled=False)


def test_metrics_render_lists_every_declared_instrument_when_enabled() -> None:
    metrics.configure(enabled=True)
    try:
        # Touch each declared instrument so it is materialised for rendering.
        for name in _ALL_INSTRUMENT_NAMES:
            getattr(metrics, name)
        body = metrics.render()
        for name in _ALL_INSTRUMENT_NAMES:
            assert f"# HELP {name}".encode() in body, name
    finally:
        metrics.configure(enabled=False)


def test_metrics_unknown_instrument_is_noop_when_enabled() -> None:
    metrics.configure(enabled=True)
    try:
        metrics.nonexistent_metric.inc()
        assert isinstance(metrics.nonexistent_metric, NoopInstrument)
    finally:
        metrics.configure(enabled=False)


def test_metrics_reconfigure_resets_registry() -> None:
    metrics.configure(enabled=True)
    metrics.http_requests_total.labels(method="GET", status="200").inc()
    assert b"http_requests_total" in metrics.render()

    metrics.configure(enabled=False)
    assert metrics.render() == b""
    assert isinstance(metrics.http_requests_total, NoopInstrument)


async def test_metrics_middleware_records_http_request() -> None:
    metrics.configure(enabled=True)
    try:
        transport = httpx.ASGITransport(app=MetricsMiddleware(_echo_correlation_app))
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get("/ping")
        assert resp.status_code == 200
        body = metrics.render()
        assert b'http_requests_total{method="GET",status="200"} 1.0' in body
        assert b"http_request_duration_seconds_count" in body
    finally:
        metrics.configure(enabled=False)


async def _echo_correlation_app(scope, receive, send) -> None:
    body = json.dumps(get_correlation()).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send({"type": "http.response.body", "body": body})


async def test_middleware_stamps_request_correlation() -> None:
    transport = httpx.ASGITransport(app=TraceIDMiddleware(_echo_correlation_app))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        resp = await client.get("/ping")
    assert resp.status_code == 200
    data = resp.json()
    assert data["trace_id"]
    assert data["request_id"] == data["trace_id"]


async def test_middleware_bridges_x_request_id() -> None:
    transport = httpx.ASGITransport(app=TraceIDMiddleware(_echo_correlation_app))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        resp = await client.get("/ping", headers={"X-Request-ID": "edge-42"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["trace_id"] == "edge-42"
    assert data["request_id"] == "edge-42"


@pytest.mark.parametrize("test", [
    "test_json_formatter_emits_valid_structured_record",
    "test_log_context_merges_nested_and_cleans_up",
])
def test_facade_import_surface_exposes_expected_names(test: str) -> None:
    # Guard against the facade accidentally losing its exports.
    import gateway.core.observability as obs

    for name in ("tracer", "metrics", "log_context", "init_observability"):
        assert hasattr(obs, name)
