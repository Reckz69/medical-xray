"""Retention cleanup: permanently purge soft-deleted scans (ADR-009).

The gateway soft-deletes scans (and cancels their in-flight jobs); after
`scan_purge_days` the scheduler hard-deletes the scan, its jobs, its output
rows and objects, and removes the underlying S3 objects. Idempotent: a scan is
purged exactly once because the rows are gone on the next cycle.

S3 deletion is best-effort — a storage outage must not block DB cleanup; the
DB is the source of truth for retention.

`CleanupService.run_cleanup` is the single entry point for the entire cleanup
pass. It is triggered from exactly two sources (both share this implementation):

* the scheduler's internal timer (the production default), and
* the `cleanup.run` command consumer (the operational interface for manual or
  scheduled cleanup requests).

A Redis distributed lock serializes runs so concurrent timers / commands /
future CronJobs never purge in parallel.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from gateway.core.config import settings
from gateway.core.db import SessionLocal
from gateway.core.redis import redis
from gateway.core.storage.factory import storage
from gateway.repositories.scan_repository import ScanRepository
from scheduler.metrics import metrics

logger = logging.getLogger("denoise.scheduler")

#: Redis key guarding concurrent cleanup runs (shared by every scheduler).
CLEANUP_LOCK_KEY = "scheduler:cleanup:lock"

_RELEASE_LOCK_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""


async def purge_soft_deleted(session: AsyncSession, *, now: datetime | None = None) -> int:
    """Permanently delete soft-deleted scans past the retention window."""
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=settings.scan_purge_days)
    scan_repo = ScanRepository(session)
    scans = await scan_repo.list_purgeable(cutoff, limit=settings.cleanup_batch_size)

    purged = 0
    for scan in scans:
        keys = [output.object.object_key for output in scan.outputs if output.object]
        await _delete_objects(keys)
        await scan_repo.purge(scan.id)
        metrics.scans_purged += 1
        metrics.objects_purged += len(keys)
        purged += 1
        logger.info("purged scan %s (deleted %s)", scan.id, scan.deleted_at)

    if purged:
        logger.info("purged %d soft-deleted scan(s)", purged)
    return purged


async def _delete_objects(keys: list[str]) -> None:
    """Best-effort S3 deletion; failures are logged, never raised."""
    for key in keys:
        try:
            await storage.delete(key)
        except Exception as exc:  # noqa: BLE001 — storage must not block DB cleanup
            metrics.last_error = f"object delete failed for {key}: {exc}"
            metrics.cleanup_failures += 1
            logger.warning("failed to delete object %s from storage: %s", key, exc)


class CleanupService:
    """Runs the cleanup pass with a distributed lock and run metrics.

    Both triggers (internal timer and the `cleanup.run` consumer) call
    :meth:`run_cleanup`, so the cleanup logic lives in exactly one place. The
    timer is the production default; a future CronJob / EventBridge / admin API
    can drive the same pass via `cleanup.run` without changing this code.
    """

    def __init__(
        self,
        *,
        lock_ttl_seconds: int | None = None,
        redis_client: Any | None = None,
    ) -> None:
        self._lock_ttl_ms = (
            lock_ttl_seconds or settings.scheduler_cleanup_lock_ttl_seconds
        ) * 1000
        self._redis = redis_client or redis

    async def run_cleanup(
        self,
        *,
        source: str,
        now: datetime | None = None,
    ) -> dict:
        """One full cleanup pass. Never raises; returns a run report."""
        started = time.perf_counter()
        token = uuid.uuid4().hex

        lock_state = await self._acquire_lock(token)
        if lock_state is not True:
            return {
                "source": source,
                "purged": 0,
                "skipped": True,
                "duration_seconds": None,
                "reason": "lock_error" if lock_state is None else "lock_held",
            }

        try:
            now = now or datetime.now(UTC)
            async with SessionLocal() as session:
                purged = await purge_soft_deleted(session, now=now)
                await session.commit()
            duration = time.perf_counter() - started
            metrics.cleanup_duration_seconds = duration
            logger.info(
                "cleanup run (source=%s) purged %d scan(s) in %.3fs",
                source,
                purged,
                duration,
            )
            return {
                "source": source,
                "purged": purged,
                "skipped": False,
                "duration_seconds": duration,
            }
        except Exception as exc:
            metrics.cleanup_failures += 1
            metrics.last_error = f"cleanup ({source}) failed: {exc}"
            logger.exception("cleanup run (source=%s) failed", source)
            return {
                "source": source,
                "purged": 0,
                "skipped": False,
                "duration_seconds": None,
                "error": str(exc),
            }
        finally:
            await self._release_lock(token)

    async def _acquire_lock(self, token: str) -> bool | None:
        """Acquire the distributed lock.

        Returns True on success, False if another run holds it, None on a Redis
        error (the run is skipped rather than risk a concurrent purge).
        """
        try:
            acquired = await self._redis.set(
                CLEANUP_LOCK_KEY, token, nx=True, px=self._lock_ttl_ms
            )
        except Exception as exc:  # noqa: BLE001
            metrics.cleanup_failures += 1
            metrics.last_error = f"cleanup lock acquire failed: {exc}"
            logger.warning("cleanup lock acquire failed (run skipped): %s", exc)
            return None
        if not acquired:
            metrics.cleanup_skipped_runs += 1
            logger.info("cleanup skipped: another run holds the lock")
            return False
        return True

    async def _release_lock(self, token: str) -> None:
        """Release the lock only if we still own it (compare-and-delete)."""
        try:
            await self._redis.eval(_RELEASE_LOCK_SCRIPT, 1, CLEANUP_LOCK_KEY, token)
        except Exception as exc:  # noqa: BLE001 — TTL will clear it if we cannot
            logger.warning("cleanup lock release failed: %s", exc)


#: Process-wide singleton used by the scheduler loops and the cleanup.run consumer.
cleanup_service = CleanupService()
