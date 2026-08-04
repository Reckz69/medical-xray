"""Job persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from gateway.models.job import (
    DEFAULT_MAX_ATTEMPTS,
    JOB_STATUS_FAILED,
    JOB_STATUS_QUEUED,
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
    ) -> Job:
        job = Job(
            scan_id=scan_id,
            status=JOB_STATUS_QUEUED,
            attempt=0,
            max_attempts=max_attempts,
            trace_id=trace_id or None,
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

    async def mark_retrying(self, job_id: UUID, *, next_retry_at: datetime) -> Job | None:
        job = await self.session.get(Job, job_id)
        if job is None:
            return None
        job.status = "RETRYING"
        job.next_retry_at = next_retry_at
        await self.session.flush()
        return job

    async def increment_attempt(self, job_id: UUID) -> Job | None:
        job = await self.session.get(Job, job_id)
        if job is None:
            return None
        job.attempt += 1
        await self.session.flush()
        return job

    async def claim_started(self, job_id: UUID, *, worker_id: str) -> Job | None:
        job = await self.session.get(Job, job_id)
        if job is None:
            return None
        job.status = "RUNNING"
        job.worker_id = worker_id
        job.started_at = datetime.now(UTC)
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
