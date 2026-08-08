"""Worker heartbeat loop (Sprint 4F).

Starts the Redis heartbeat + registry task for a running worker. The schema
and Redis helpers live in ``gateway.core.worker_registry`` so the gateway and
worker stay in agreement; this module only owns the periodic cadence.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from gateway.core.config import settings
from gateway.core.worker_registry import register, unregister, write_heartbeat

logger = logging.getLogger("denoise.worker")


async def heartbeat_loop(model: Any) -> None:
    """Background task: register once, refresh on an interval, unregister."""
    await register()
    started = time.monotonic()
    try:
        while True:
            await write_heartbeat(model, uptime_seconds=time.monotonic() - started)
            await asyncio.sleep(settings.worker_heartbeat_interval_seconds)
    finally:
        await unregister()
