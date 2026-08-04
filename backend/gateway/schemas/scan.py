"""Scan API request / response schemas (OpenAPI-aligned)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


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


class ScanListOut(BaseModel):
    items: list[ScanOut]
    total: int
    offset: int
    limit: int


class UploadScanResponse(BaseModel):
    scan: ScanOut
    job_id: UUID
    job_status: str
