"""Structured JSON logging + correlation context.

Replaces the plain-text formatter with machine-readable JSON records that carry
the correlation fields needed to answer "what happened for this request":

    trace_id, span_id, request_id, scan_id, job_id, user_id, service

Correlation is stored in a :mod:`contextvars` variable so each async task /
message handler carries its own context. Three ways to set it:

* ``set_correlation(**fields)`` — merge fields into the current task's context
  (used for request-scoped correlation, e.g. user_id after auth).
* ``log_context(**fields)`` — a context manager that sets fields for a block and
  restores the previous context on exit (worker message handlers, scheduler
  cycles, middleware request handling).
* ``init_observability(service=...)`` — sets the process-wide ``service`` field.

``trace_id`` / ``span_id`` prefer the active OpenTelemetry span (via the
``tracer`` facade) when tracing is enabled; otherwise they fall back to the
correlation context set by the gateway's TraceIDMiddleware.
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from gateway.core.observability.tracing import tracer

#: Correlation fields for the current task. Never mutated in place — always
#: replaced with a new dict so nested log_context scopes can restore tokens.
_CORRELATION: ContextVar[dict[str, str] | None] = ContextVar(
    "observability.correlation", default=None
)

#: Fields emitted as first-class JSON keys when present.
_CORRELATION_FIELDS = (
    "service",
    "trace_id",
    "span_id",
    "request_id",
    "scan_id",
    "job_id",
    "user_id",
)


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per log record (UTC timestamp, structured fields)."""

    def format(self, record: logging.LogRecord) -> str:
        correlation = get_correlation()
        entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        trace_id, span_id = tracer.get_current_span_context()
        if trace_id:
            entry["trace_id"] = trace_id
        elif correlation.get("trace_id"):
            entry["trace_id"] = correlation["trace_id"]
        if span_id:
            entry["span_id"] = span_id

        for field in _CORRELATION_FIELDS:
            value = correlation.get(field)
            if value:
                entry[field] = value

        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Install the JSON handler on the root logger (replaces prior handlers)."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.setLevel(level.upper())
    root.handlers = [handler]


def get_correlation() -> dict[str, str]:
    """Snapshot of the current task's correlation fields (a copy)."""
    return dict(_CORRELATION.get() or {})


def set_correlation(**fields: str) -> None:
    """Merge ``fields`` into the current task's correlation context.

    Values that are ``None`` are ignored; empty strings are kept out. No token
    is returned — this is for task-scoped values (e.g. ``user_id`` after auth)
    that should live for the rest of the request.
    """
    current = get_correlation()
    for key, value in fields.items():
        if value is not None and value != "":
            current[key] = str(value)
    _CORRELATION.set(current)


@contextmanager
def log_context(**fields: str) -> Iterator[None]:
    """Set correlation ``fields`` for this block, restoring the prior context.

    Nested calls merge: an inner scope sees the outer fields too, and exiting
    the inner scope restores exactly the outer context.
    """
    merged = get_correlation()
    for key, value in fields.items():
        if value is not None and value != "":
            merged[key] = str(value)
    token = _CORRELATION.set(merged)
    try:
        yield
    finally:
        _CORRELATION.reset(token)
