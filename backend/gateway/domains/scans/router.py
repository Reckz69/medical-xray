"""Scans API router.

Mounts under ``{api_prefix}/scans`` in main.py.
Endpoints: upload, list, get, soft-delete.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.core.db import get_db
from gateway.core.deps import AuditLoggerDeps, CurrentUserDeps
from gateway.core.envelope import envelope
from gateway.core.otel import get_trace_id
from gateway.core.storage import get_storage_provider
from gateway.core.storage.base import StorageProvider
from gateway.domains.scans import service as scan_svc
from gateway.schemas.scan import ScanListOut, ScanOut, UploadScanResponse

router = APIRouter(prefix="/scans", tags=["Scans"])


# ── POST /scans ──────────────────────────────────────────────────────────
@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def upload_scan(
    request: Request,
    current_user: CurrentUserDeps,
    audit: AuditLoggerDeps,
    file: UploadFile = File(...),  # noqa: B008
    session: AsyncSession = Depends(get_db),  # noqa: B008
    storage: StorageProvider = Depends(get_storage_provider),  # noqa: B008
) -> dict:
    result = await scan_svc.upload_scan(
        session,
        storage=storage,
        current_user=current_user,
        audit=audit,
        filename=file.filename or "",
        data=await file.read(),
        trace_id=get_trace_id(request),
    )
    return envelope(
        data=UploadScanResponse(
            scan=ScanOut.model_validate(result["scan"], from_attributes=True),
            job_id=result["job"].id,
            job_status=result["job"].status,
        ),
        trace_id=get_trace_id(request),
    )


# ── GET /scans ───────────────────────────────────────────────────────────
@router.get("")
async def list_scans(
    request: Request,
    current_user: CurrentUserDeps,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),  # noqa: B008
) -> dict:
    result = await scan_svc.list_scans(
        session,
        current_user=current_user,
        offset=offset,
        limit=limit,
    )
    return envelope(
        data=ScanListOut(
            items=[
                ScanOut.model_validate(scan, from_attributes=True)
                for scan in result["items"]
            ],
            total=result["total"],
            offset=offset,
            limit=limit,
        ),
        trace_id=get_trace_id(request),
    )


# ── GET /scans/{id} ──────────────────────────────────────────────────────
@router.get("/{scan_id}")
async def get_scan(
    request: Request,
    scan_id: UUID,
    current_user: CurrentUserDeps,
    session: AsyncSession = Depends(get_db),  # noqa: B008
) -> dict:
    scan = await scan_svc.get_scan(
        session,
        current_user=current_user,
        scan_id=scan_id,
    )
    return envelope(
        data=ScanOut.model_validate(scan, from_attributes=True),
        trace_id=get_trace_id(request),
    )


# ── DELETE /scans/{id} (soft delete) ─────────────────────────────────────
@router.delete("/{scan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scan(
    request: Request,
    scan_id: UUID,
    current_user: CurrentUserDeps,
    audit: AuditLoggerDeps,
    session: AsyncSession = Depends(get_db),  # noqa: B008
) -> None:
    await scan_svc.delete_scan(
        session,
        current_user=current_user,
        audit=audit,
        scan_id=scan_id,
    )
