"""Command handlers for the scheduler — dispatch to the cleanup service.

The scheduler consumes the `cleanup.run` routing key on the `commands` exchange;
each command triggers the same `CleanupService.run_cleanup` pass as the internal
timer (ADR-009). The timer remains the default; `cleanup.run` is the operational
interface for manual or automated cleanup requests.
"""

from __future__ import annotations

import logging
from typing import Any

from scheduler.cleanup import CleanupService, cleanup_service

logger = logging.getLogger("denoise.scheduler")


async def handle_cleanup_run(
    payload: dict[str, Any],
    *,
    trace_id: str = "",
    correlation_id: str = "",
    service: CleanupService | None = None,
) -> dict:
    """Run the cleanup pass once (distributed lock, metrics, idempotent)."""
    svc = service or cleanup_service
    result = await svc.run_cleanup(source="cleanup.run")
    if result.get("error"):
        logger.error(
            "cleanup.run handler error: %s", result["error"]
        )
    return result
