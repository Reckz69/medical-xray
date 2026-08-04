"""Scan API request / response schemas (OpenAPI-aligned)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ScanOutputOut(BaseModel):
    """Metadata for one persisted output (no URL — fetch per action, ADR-003)."""

    type: str
    mime_type: str
    size_bytes: int
    checksum: str | None = None


class ScanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    user_id: UUID
    status: str
    original_name: str
    format: str
    size_bytes: int
    content_hash: str
    width: int
    height: int
    created_at: datetime
    deleted_at: datetime | None = None

    model_id: UUID | None = None
    noise_variance: float | None = None
    routing_message: str | None = None
    was_bypassed: bool = False
    processing_time_ms: float | None = None
    completed_at: datetime | None = None

    # Populated by the service after validation (output metadata lives on the
    # linked Object, not the ScanOutput row). `validation_alias` prevents the
    # ORM's relationship attribute from being read during model_validate.
    outputs: list[ScanOutputOut] = Field(
        default_factory=list, validation_alias="__outputs__"
    )


class ScanListOut(BaseModel):
    items: list[ScanOut]
    total: int
    offset: int
    limit: int


class UploadScanResponse(BaseModel):
    scan: ScanOut
    job_id: UUID | None = None
    job_status: str | None = None
    duplicate: bool = False
    message: str | None = None


class ScanOutputUrlOut(BaseModel):
    output_type: str
    download_url: str
    content_type: str
    expires_in: int  # seconds until the presigned URL expires
