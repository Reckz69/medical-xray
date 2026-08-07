"""Trace/request correlation for the gateway.

Sprint 1 keeps this dependency-free: a small ASGI middleware that mints a
W3C-compatible `trace_id` (from the incoming `traceparent` header, or a new
random one) and attaches it to `request.state`. `X-Request-ID` from the edge
is bridged to the same value.

The trace_id is:
  - returned in every envelope (`meta.trace_id` / `trace_id` field),
  - persisted on `jobs.trace_id` and `audit_logs.trace_id`,
  - propagated into RabbitMQ message headers for the worker.

Full OpenTelemetry SDK wiring (spans, exporters, collector) lands in Sprint 4
and builds on top of this same identifier.
"""

import re
import uuid

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from gateway.core.observability import log_context, tracer

#: W3C traceparent: version 00, 32-hex trace id, 16-hex span id, any flags
#: byte (flags bit 0 = sampled; OTel emits 0x01/0x03, both accepted here).
_TRACEPARENT_RE = re.compile(r"^00-([0-9a-f]{32})-(?:[0-9a-f]{16})-([0-9a-f]{2})$")

#: Header the gateway emits/echoes so edge proxies and the client can correlate.
REQUEST_ID_HEADER = "x-request-id"


def new_trace_id() -> str:
    return uuid.uuid4().hex


def parse_traceparent(header: str | None) -> str | None:
    """Extract the W3C trace id from a traceparent header, if well-formed."""
    if not header:
        return None
    m = _TRACEPARENT_RE.match(header.strip())
    return m.group(1) if m else None


def get_trace_id(request: Request) -> str:
    """Return the request's trace id (always present after middleware)."""
    return getattr(request.state, "trace_id", "") or ""


class TraceIDMiddleware:
    """Assign `trace_id` to every request, echo it as `X-Request-ID`, and span it.

    When tracing is enabled the request runs inside a span that continues the
    incoming ``traceparent`` (or starts a fresh root), and the active span's
    trace id becomes the correlation ``trace_id`` so the envelope, logs, and
    RabbitMQ headers all agree. When disabled, the middleware mints the
    correlation ``trace_id`` as before and the span wrapper is a no-op.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        method = scope.get("method", "")
        trace_id = (
            request.headers.get(REQUEST_ID_HEADER)
            or parse_traceparent(request.headers.get("traceparent"))
            or new_trace_id()
        )
        request.state.trace_id = trace_id

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.get("headers", [])
                message["headers"] = list(headers) + [
                    (REQUEST_ID_HEADER.encode(), request.state.trace_id.encode())
                ]
            await send(message)

        with tracer.span_from_traceparent(
            request.headers.get("traceparent"),
            name=f"{method} {request.url.path}",
            attributes={
                "http.method": method,
                "http.url": str(request.url),
                "http.target": request.url.path,
            },
        ):
            # Tracing on: prefer the OTel trace id so every correlation surface
            # (envelope, logs, AMQP headers) carries the same trace.
            span_trace_id, _ = tracer.get_current_span_context()
            if span_trace_id:
                request.state.trace_id = span_trace_id
            with log_context(trace_id=request.state.trace_id, request_id=request.state.trace_id):
                await self.app(scope, receive, send_wrapper)
