"""Retention cleanup: permanently purge soft-deleted scans (ADR-009).

The gateway soft-deletes scans (and cancels their in-flight jobs); after
`scan_purge_days` the scheduler hard-deletes the scan, its jobs, its output
rows and objects, and removes the underlying S3 objects. Idempotent: a scan is
purged exactly once because the rows are gone on the next cycle.

S3 deletion is best-effort — a storage outage must not block DB cleanup; the
DB is the source of truth for retention.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from gateway.core.config import settings
from gateway.core.storage.factory import storage
from gateway.repositories.scan_repository import ScanRepository
from scheduler.metrics import metrics

logger = logging.getLogger("denoise.scheduler")


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
            logger.warning("failed to delete object %s from storage: %s", key, exc)
