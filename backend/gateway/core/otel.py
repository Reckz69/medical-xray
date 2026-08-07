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

from gateway.core.observability.logging import log_context

_TRACEPARENT_RE = re.compile(r"^00-([0-9a-f]{32})-(?:[0-9a-f]{16})-01$")

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
    """Assign `trace_id` to every request and echo it as `X-Request-ID`."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
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
                    (REQUEST_ID_HEADER.encode(), trace_id.encode())
                ]
            await send(message)

        with log_context(trace_id=trace_id, request_id=trace_id):
            await self.app(scope, receive, send_wrapper)
