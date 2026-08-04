"""Job API response schema (OpenAPI-aligned)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class JobOut(BaseModel):
    id: UUID
    scan_id: UUID
    status: str
    attempt: int
    max_attempts: int
    worker_id: str | None = None
    error: str | None = None
    trace_id: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    next_retry_at: datetime | None = None

    # Convenience for polling: the owning scan's lifecycle status.
    scan_status: str
