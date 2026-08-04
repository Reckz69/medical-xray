"""Jobs API router.

Mounts under ``{api_prefix}/jobs`` in main.py.
Endpoints: get job status (for upload -> queued -> running -> completed polling).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.core.db import get_db
from gateway.core.deps import CurrentUserDeps
from gateway.core.envelope import envelope
from gateway.core.otel import get_trace_id
from gateway.domains.jobs import service as job_svc
from gateway.schemas.job import JobOut

router = APIRouter(prefix="/jobs", tags=["Jobs"])


# ── GET /jobs/{job_id} ────────────────────────────────────────────────────
@router.get("/{job_id}")
async def get_job(
    request: Request,
    job_id: UUID,
    current_user: CurrentUserDeps,
    session: AsyncSession = Depends(get_db),  # noqa: B008
) -> dict:
    data = await job_svc.get_job(
        session,
        current_user=current_user,
        job_id=job_id,
    )
    return envelope(
        data=JobOut(**data),
        trace_id=get_trace_id(request),
    )
