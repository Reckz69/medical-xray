"""Job retry + stall recovery (ADR-009, scheduler poll loop).

Two recovery passes, both idempotent when multiple schedulers run:

* ``republish_retries`` — RETRYING jobs past ``next_retry_at`` are re-issued as
  ``inference.run`` commands from their persisted payload, then the republish
  marker is cleared (job back to QUEUED waiting for a worker).
* ``recover_stalled`` — RUNNING jobs whose claim is older than the stall
  timeout (worker died mid-job) re-enter the retry pipeline, or go terminal
  FAILED when the attempt cap is exhausted.
* ``recover_unconfirmed`` — QUEUED jobs whose republish was claimed but never
  confirmed (scheduler crash mid-publish) are republished again. At-least-once
  delivery is safe because the worker's claim is atomic (see
  ``JobRepository.claim_for_execution``).

Publish failures never lose a job: the job is marked RETRYING due-immediately
and picked up on the next cycle.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from gateway.core.config import settings
from gateway.core.queue import (
    CMD_INFERENCE_RUN,
    EVT_SCAN_FAILED,
    queue,
)
from gateway.repositories.job_repository import JobRepository
from gateway.repositories.scan_repository import ScanRepository
from scheduler.metrics import metrics

logger = logging.getLogger("denoise.scheduler")

_MAX_ERROR = 2000


def backoff_seconds(attempt: int) -> int:
    """Exponential backoff for the attempt that just failed (ADR-009)."""
    base = settings.job_retry_backoff_base_seconds
    cap = settings.job_retry_backoff_max_seconds
    return min(base * 2 ** (attempt - 1), cap)


async def _republish(
    session: AsyncSession, repo: JobRepository, job, *, trace_id: str
) -> None:
    """Publish a retry command, or terminal-fail the job if it has no payload."""
    if not job.payload:
        await repo.mark_failed(job.id, error="retry dropped: job has no persisted payload")
        metrics.jobs_payload_missing += 1
        return
    try:
        await queue.publish_command(
            CMD_INFERENCE_RUN, job.payload, trace_id=trace_id or job.trace_id or ""
        )
    except Exception as exc:  # noqa: BLE001 — a broker outage must not lose the job
        await repo.mark_retrying(
            job.id, next_retry_at=datetime.now(UTC), error=f"republish failed: {exc}"
        )
        metrics.last_error = f"republish failed for {job.id}: {exc}"
        logger.warning(
            "failed to republish inference.run for job %s: %s", job.id, exc
        )
        return
    await repo.confirm_republished(job.id)
    metrics.jobs_republished += 1


async def republish_retries(session: AsyncSession, *, now: datetime | None = None) -> int:
    """Re-issue `inference.run` for RETRYING jobs whose backoff has elapsed."""
    now = now or datetime.now(UTC)
    repo = JobRepository(session)
    due = await repo.list_retryable_due(now=now)
    count = 0
    for job in due:
        if not await repo.claim_republish(job.id, now=now):
            continue  # a concurrent scheduler already claimed it
        await _republish(session, repo, job, trace_id=job.trace_id or "")
        count += 1
    return count


async def recover_unconfirmed(session: AsyncSession, *, now: datetime | None = None) -> int:
    """Republish QUEUED jobs whose republish marker was never confirmed."""
    now = now or datetime.now(UTC)
    repo = JobRepository(session)
    unconfirmed = await repo.list_unconfirmed(
        now, grace_seconds=settings.scheduler_poll_interval_seconds
    )
    count = 0
    for job in unconfirmed:
        await _republish(session, repo, job, trace_id=job.trace_id or "")
        count += 1
    return count


async def recover_stalled(session: AsyncSession, *, now: datetime | None = None) -> int:
    """Return RUNNING jobs with an expired claim to the retry pipeline."""
    now = now or datetime.now(UTC)
    repo = JobRepository(session)
    stalled = await repo.list_stalled(settings.job_stall_timeout_seconds, now=now)
    recovered = 0
    for job in stalled:
        if job.attempt < job.max_attempts:
            next_retry_at = now + timedelta(seconds=backoff_seconds(job.attempt))
            if not await repo.recover_stalled_retry(
                job.id,
                now=now,
                stall_seconds=settings.job_stall_timeout_seconds,
                next_retry_at=next_retry_at,
                error="stalled: worker lost while RUNNING",
            ):
                continue  # a concurrent scheduler already recovered it
            metrics.jobs_recovered += 1
            recovered += 1
            logger.warning(
                "job %s stalled (RUNNING %s); retrying at %s",
                job.id, job.started_at, next_retry_at.isoformat(),
            )
        else:
            if not await repo.recover_stalled_fail(
                job.id,
                now=now,
                stall_seconds=settings.job_stall_timeout_seconds,
                error="stalled: attempts exhausted (worker lost)",
            ):
                continue
            metrics.jobs_failed_terminal += 1
            await ScanRepository(session).set_failed(
                job.scan_id, routing_message="stalled: attempts exhausted (worker lost)"
            )
            await _publish_stalled_failed(job, error="stalled: attempts exhausted (worker lost)")
            logger.error("job %s failed: stalled at attempt cap", job.id)
    return recovered


async def _publish_stalled_failed(job, *, error: str) -> None:
    """Publish a scan.failed event for a terminal stall recovery."""
    event = {
        "scan_id": str(job.scan_id),
        "job_id": str(job.id),
        "status": "FAILED",
        "format": job.payload.get("format") if job.payload else None,
        "original_name": job.payload.get("original_name") if job.payload else None,
        "object_key": job.payload.get("object_key") if job.payload else None,
        "error": error,
    }
    try:
        await queue.publish_event(EVT_SCAN_FAILED, event, trace_id=job.trace_id or "")
    except Exception as exc:  # noqa: BLE001 — broker outage must not crash the scheduler
        logger.warning("failed to publish %s for scan %s: %s", EVT_SCAN_FAILED, job.scan_id, exc)


async def run_once(session: AsyncSession, *, now: datetime | None = None) -> dict:
    """One scheduler cycle: republish retries, recover stalls, confirm stragglers."""
    now = now or datetime.now(UTC)
    republished = await republish_retries(session, now=now)
    recovered = await recover_stalled(session, now=now)
    unconfirmed = await recover_unconfirmed(session, now=now)
    return {
        "jobs_republished": republished,
        "jobs_recovered": recovered,
        "jobs_republished_unconfirmed": unconfirmed,
    }
