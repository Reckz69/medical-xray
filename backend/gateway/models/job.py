"""Job — one inference attempt per scan, with retry bookkeeping."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gateway.models.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from gateway.models.scan import Scan

JOB_STATUS_QUEUED = "QUEUED"
JOB_STATUS_RUNNING = "RUNNING"
JOB_STATUS_FAILED = "FAILED"
JOB_STATUS_RETRYING = "RETRYING"
JOB_STATUS_COMPLETED = "COMPLETED"
JOB_STATUS_CANCELLED = "CANCELLED"

DEFAULT_MAX_ATTEMPTS = 3


class Job(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_status_created_at", "status", "created_at"),
        Index("ix_jobs_scan_id", "scan_id"),
    )

    scan_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("scans.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text(f"'{JOB_STATUS_QUEUED}'")
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("3")
    )
    worker_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    scan: Mapped[Scan] = relationship(back_populates="jobs")
