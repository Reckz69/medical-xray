"""Scan, ScanOutput, Object.

`scan_outputs` is normalized (one row per output type — adding super-res,
segmentation, or a report PDF later is an insert, not a migration). `objects`
is storage-agnostic: bucket/key/etag/checksum only.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gateway.models.base import (
    Base,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

if TYPE_CHECKING:
    from gateway.models.job import Job
    from gateway.models.model_version import ModelVersion
    from gateway.models.organization import Organization
    from gateway.models.user import User

SCAN_STATUS_QUEUED = "QUEUED"
SCAN_STATUS_RUNNING = "RUNNING"
SCAN_STATUS_COMPLETED = "COMPLETED"
SCAN_STATUS_FAILED = "FAILED"
SCAN_STATUS_CANCELLED = "CANCELLED"

FORMAT_PNG = "PNG"
FORMAT_JPEG = "JPEG"
FORMAT_DICOM = "DICOM"

OUTPUT_TYPE_ORIGINAL = "ORIGINAL"
OUTPUT_TYPE_NOISE_MAP = "NOISE_MAP"
OUTPUT_TYPE_UNET = "UNET"
OUTPUT_TYPE_ENHANCED = "ENHANCED"

LIFECYCLE_ACTIVE = "ACTIVE"
LIFECYCLE_ARCHIVED = "ARCHIVED"
LIFECYCLE_DELETED = "DELETED"

STORAGE_CLASS_STANDARD = "STANDARD"
STORAGE_CLASS_GLACIER = "GLACIER"


class Scan(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "scans"
    __table_args__ = (
        Index(
            "uq_scans_org_content_hash_active",
            "organization_id",
            "content_hash",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_scans_user_id_created_at", "user_id", text("created_at DESC")),
        Index("ix_scans_status", "status"),
        Index("ix_scans_deleted_at", "deleted_at"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    model_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("model_versions.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text(f"'{SCAN_STATUS_QUEUED}'")
    )
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    format: Mapped[str] = mapped_column(String(10), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # sha256
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    noise_variance: Mapped[float | None] = mapped_column(Float, nullable=True)
    routing_message: Mapped[str | None] = mapped_column(String(255), nullable=True)
    was_bypassed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    processing_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    storage_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    organization: Mapped[Organization] = relationship(back_populates="scans")
    user: Mapped[User] = relationship(back_populates="scans", foreign_keys=[user_id])
    model_version: Mapped[ModelVersion | None] = relationship(back_populates="scans")
    outputs: Mapped[list[ScanOutput]] = relationship(
        back_populates="scan", cascade="all, delete-orphan"
    )
    jobs: Mapped[list[Job]] = relationship(back_populates="scan")


class ScanOutput(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "scan_outputs"
    __table_args__ = (
        UniqueConstraint("scan_id", "type", name="uq_scan_outputs_scan_type"),
    )

    scan_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("scans.id"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    object_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("objects.id"), nullable=False
    )

    scan: Mapped[Scan] = relationship(back_populates="outputs")
    object: Mapped[Object] = relationship(back_populates="scan_outputs")


class Object(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "objects"
    __table_args__ = (
        Index("ix_objects_object_key", "object_key"),
        Index("ix_objects_lifecycle_state", "lifecycle_state"),
    )

    bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    etag: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime_type: Mapped[str] = mapped_column(
        String(100), nullable=False, server_default=text("'application/octet-stream'")
    )
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)  # sha256
    storage_class: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text(f"'{STORAGE_CLASS_STANDARD}'")
    )
    encrypted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    lifecycle_state: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text(f"'{LIFECYCLE_ACTIVE}'")
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    scan_outputs: Mapped[list[ScanOutput]] = relationship(back_populates="object")
