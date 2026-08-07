"""Job persistence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from gateway.models.job import (
    DEFAULT_MAX_ATTEMPTS,
    JOB_STATUS_FAILED,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RETRYING,
    JOB_STATUS_RUNNING,
    JOB_STATUS_CANCELLED,
    Job,
)
from gateway.models.scan import Scan
from gateway.repositories.base import BaseRepository


class JobRepository(BaseRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def create(
        self,
        *,
        scan_id: UUID,
        trace_id: str = "",
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        payload: dict[str, Any] | None = None,
    ) -> Job:
        job = Job(
            scan_id=scan_id,
            status=JOB_STATUS_QUEUED,
            attempt=0,
            max_attempts=max_attempts,
            trace_id=trace_id or None,
            payload=payload,
        )
        self.session.add(job)
        await self.session.flush()
        return job

    async def get_by_id(self, job_id: UUID) -> Job | None:
        return await self.session.get(Job, job_id)

    async def get_by_scan_id(self, scan_id: UUID) -> Job | None:
        result = await self.session.execute(
            select(Job)
            .where(Job.scan_id == scan_id)
            .order_by(Job.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_for_user(self, job_id: UUID, user_id: UUID) -> Job | None:
        """Fetch a job the given user owns (via its scan); None if foreign/missing."""
        result = await self.session.execute(
            select(Job)
            .join(Scan, Scan.id == Job.scan_id)
            .options(joinedload(Job.scan))
            .where(
                Job.id == job_id,
                Scan.user_id == user_id,
                Scan.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def mark_failed(
        self,
        job_id: UUID,
        *,
        error: str,
        next_retry_at: datetime | None = None,
        status: str = JOB_STATUS_FAILED,
    ) -> Job | None:
        job = await self.session.get(Job, job_id)
        if job is None:
            return None
        job.status = status
        job.error = error[:2000]
        job.next_retry_at = next_retry_at
        job.finished_at = datetime.now(UTC)
        await self.session.flush()
        return job

    async def mark_retrying(
        self,
        job_id: UUID,
        *,
        next_retry_at: datetime,
        error: str | None = None,
    ) -> Job | None:
        job = await self.session.get(Job, job_id)
        if job is None:
            return None
        job.status = JOB_STATUS_RETRYING
        job.next_retry_at = next_retry_at
        if error is not None:
            job.error = error[:2000]
        await self.session.flush()
        return job

    async def claim_for_execution(self, job_id: UUID, *, worker_id: str) -> bool:
        """Atomically claim a QUEUED/RETRYING job for execution.

        Guards the worker against duplicate or re-delivered messages: only one
        claim succeeds per job; a second claim (job already RUNNING or terminal)
        is a no-op (ADR-009 idempotency).
        """
        result = await self.session.execute(
            update(Job)
            .where(
                Job.id == job_id,
                Job.status.in_((JOB_STATUS_QUEUED, JOB_STATUS_RETRYING)),
            )
            .values(
                attempt=Job.attempt + 1,
                status=JOB_STATUS_RUNNING,
                worker_id=worker_id,
                started_at=datetime.now(UTC),
            )
        )
        return result.rowcount == 1

    async def claim_republish(self, job_id: UUID, *, now: datetime) -> bool:
        """Atomically claim a due RETRYING job for republishing.

        Moves it to QUEUED with `next_retry_at = now` as an in-flight marker so
        a concurrent scheduler cannot republish it too. `now` is cleared by
        `confirm_republished` once the command is durable (ADR-009).
        """
        result = await self.session.execute(
            update(Job)
            .where(Job.id == job_id, Job.status == JOB_STATUS_RETRYING)
            .values(status=JOB_STATUS_QUEUED, next_retry_at=now)
        )
        return result.rowcount == 1

    async def confirm_republished(self, job_id: UUID) -> bool:
        """Clear the republish marker after the retry command is published."""
        result = await self.session.execute(
            update(Job)
            .where(
                Job.id == job_id,
                Job.status == JOB_STATUS_QUEUED,
                Job.next_retry_at.is_not(None),
            )
            .values(next_retry_at=None)
        )
        return result.rowcount == 1

    async def list_unconfirmed(
        self, now: datetime, *, grace_seconds: int
    ) -> list[Job]:
        """QUEUED jobs whose republish was claimed but never confirmed.

        Covers a scheduler crash between `claim_republish` and
        `confirm_republished`; the command is republished on the next cycle
        (at-least-once, worker claims guard against duplicate processing).
        """
        cutoff = now - timedelta(seconds=grace_seconds)
        result = await self.session.execute(
            select(Job).where(
                Job.status == JOB_STATUS_QUEUED,
                Job.attempt > 0,
                Job.next_retry_at.is_not(None),
                Job.next_retry_at <= cutoff,
            )
        )
        return list(result.scalars().all())

    async def recover_stalled_retry(
        self,
        job_id: UUID,
        *,
        now: datetime,
        stall_seconds: int,
        next_retry_at: datetime,
        error: str,
    ) -> bool:
        """Atomically move a stalled RUNNING job to RETRYING (worker lost)."""
        cutoff = now - timedelta(seconds=stall_seconds)
        result = await self.session.execute(
            update(Job)
            .where(
                Job.id == job_id,
                Job.status == JOB_STATUS_RUNNING,
                Job.started_at.is_not(None),
                Job.started_at < cutoff,
            )
            .values(
                status=JOB_STATUS_RETRYING,
                next_retry_at=next_retry_at,
                error=error[:2000],
            )
        )
        return result.rowcount == 1

    async def recover_stalled_fail(
        self,
        job_id: UUID,
        *,
        now: datetime,
        stall_seconds: int,
        error: str,
    ) -> bool:
        """Atomically mark a stalled RUNNING job terminal FAILED (cap reached)."""
        cutoff = now - timedelta(seconds=stall_seconds)
        result = await self.session.execute(
            update(Job)
            .where(
                Job.id == job_id,
                Job.status == JOB_STATUS_RUNNING,
                Job.started_at.is_not(None),
                Job.started_at < cutoff,
            )
            .values(
                status=JOB_STATUS_FAILED,
                error=error[:2000],
                finished_at=now,
            )
        )
        return result.rowcount == 1

    async def list_stalled(
        self, stall_timeout_seconds: int, *, now: datetime | None = None
    ) -> list[Job]:
        """RUNNING jobs whose claim is older than the stall timeout (worker lost)."""
        now = now or datetime.now(UTC)
        cutoff = now - timedelta(seconds=stall_timeout_seconds)
        result = await self.session.execute(
            select(Job).where(
                Job.status == JOB_STATUS_RUNNING,
                Job.started_at.is_not(None),
                Job.started_at < cutoff,
            )
        )
        return list(result.scalars().all())

    async def list_retryable_due(self, *, now: datetime | None = None) -> list[Job]:
        """RETRYING jobs whose next_retry_at has passed and are ready to republish."""
        now = now or datetime.now(UTC)
        result = await self.session.execute(
            select(Job).where(
                Job.status == JOB_STATUS_RETRYING,
                Job.next_retry_at.is_not(None),
                Job.next_retry_at <= now,
            )
        )
        return list(result.scalars().all())

    async def mark_cancelled(self, job_id: UUID, *, error: str = "cancelled") -> Job | None:
        job = await self.session.get(Job, job_id)
        if job is None:
            return None
        job.status = JOB_STATUS_CANCELLED
        job.error = error[:2000]
        job.finished_at = datetime.now(UTC)
        await self.session.flush()
        return job

    async def mark_completed(self, job_id: UUID) -> Job | None:
        job = await self.session.get(Job, job_id)
        if job is None:
            return None
        job.status = "COMPLETED"
        job.finished_at = datetime.now(UTC)
        await self.session.flush()
        return job
