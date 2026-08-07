"""Scheduler entrypoint — periodic retry + cleanup loops (ADR-009).

Run via ``python -m scheduler.main`` or the Docker scheduler service.

* Retry pass (republish due retries, recover stalled RUNNING jobs) runs every
  ``scheduler_poll_interval_seconds``.
* Cleanup pass (purge soft-deleted scans) runs every
  ``scheduler_cleanup_interval_seconds``.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime

from gateway.core.config import settings
from gateway.core.db import SessionLocal
from gateway.core.logging import configure_logging
from scheduler import cleanup, retry_jobs
from scheduler.metrics import metrics

logger = logging.getLogger("denoise.scheduler")


async def run_once() -> dict:
    """One retry cycle (republish + stall recovery) with fresh metrics."""
    now = datetime.now(UTC)
    async with SessionLocal() as session:
        report = await retry_jobs.run_once(session, now=now)
        await session.commit()
    metrics.cycles += 1
    metrics.last_run_at = now
    logger.info("scheduler cycle: %s", report)
    return report


async def run_cleanup() -> int:
    """One cleanup pass (purge soft-deleted scans)."""
    now = datetime.now(UTC)
    async with SessionLocal() as session:
        purged = await cleanup.purge_soft_deleted(session, now=now)
        await session.commit()
    return purged


async def main() -> None:
    configure_logging("DEBUG" if settings.debug else "INFO")
    logger.info(
        "scheduler starting: poll=%ds cleanup=%ds stall=%ds",
        settings.scheduler_poll_interval_seconds,
        settings.scheduler_cleanup_interval_seconds,
        settings.job_stall_timeout_seconds,
    )

    last_cleanup = 0.0
    while True:
        cycle_started = time.monotonic()
        try:
            await run_once()
        except Exception as exc:  # noqa: BLE001 — a bad cycle must not kill the loop
            logger.exception("scheduler cycle failed")
            metrics.last_error = str(exc)

        if time.monotonic() - last_cleanup >= settings.scheduler_cleanup_interval_seconds:
            try:
                purged = await run_cleanup()
                last_cleanup = time.monotonic()
                if purged:
                    logger.info("cleanup purged %d scan(s)", purged)
            except Exception as exc:  # noqa: BLE001
                logger.exception("scheduler cleanup failed")
                metrics.last_error = str(exc)

        elapsed = time.monotonic() - cycle_started
        await asyncio.sleep(max(settings.scheduler_poll_interval_seconds - elapsed, 1))


if __name__ == "__main__":
    asyncio.run(main())
