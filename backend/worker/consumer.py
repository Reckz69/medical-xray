"""Command handlers — parse a command payload and dispatch to the executor."""

from __future__ import annotations

from typing import Any

from worker import executor


async def handle_inference_run(
    payload: dict[str, Any], *, trace_id: str = "", correlation_id: str = ""
) -> None:
    await executor.process_message(
        payload, trace_id=trace_id, correlation_id=correlation_id
    )
