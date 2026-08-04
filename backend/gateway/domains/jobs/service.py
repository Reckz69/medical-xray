"""Jobs service — read-only job status for polling (Sprint 3.5).

Users may only read their own jobs (ownership is derived through the owning
scan). A foreign or missing job is reported as 404 so callers cannot probe for
existence.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from gateway.core.errors import NotFoundError
from gateway.repositories.job_repository import JobRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from gateway.core.deps import CurrentUser


async def get_job(
    session: AsyncSession,
    *,
    current_user: CurrentUser,
    job_id: UUID,
) -> dict:
    """Fetch the current user's job with its scan status."""
    job = await JobRepository(session).get_for_user(job_id, current_user.id)
    if job is None:
        raise NotFoundError("Job not found")
    return {
        "id": job.id,
        "scan_id": job.scan_id,
        "status": job.status,
        "attempt": job.attempt,
        "max_attempts": job.max_attempts,
        "worker_id": job.worker_id,
        "error": job.error,
        "trace_id": job.trace_id,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "next_retry_at": job.next_retry_at,
        "scan_status": job.scan.status,
    }
