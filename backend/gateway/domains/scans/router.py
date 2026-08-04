"""Scans API router.

Mounts under ``{api_prefix}/scans`` in main.py.
Endpoints: upload, list, get, output download URL, soft-delete.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.core.db import get_db
from gateway.core.deps import (
    AuditLoggerDeps,
    CurrentUserDeps,
    enforce_download_rate_limit,
    enforce_upload_rate_limit,
)
from gateway.core.envelope import envelope
from gateway.core.otel import get_trace_id
from gateway.core.storage import get_storage_provider
from gateway.core.storage.base import StorageProvider
from gateway.domains.scans import service as scan_svc
from gateway.schemas.scan import (
    ScanListOut,
    ScanOut,
    ScanOutputOut,
    ScanOutputUrlOut,
    UploadScanResponse,
)

router = APIRouter(prefix="/scans", tags=["Scans"])


def _with_outputs(scan_out: ScanOut, outputs: list) -> ScanOut:
    scan_out.outputs = [
        ScanOutputOut(
            type=o.type,
            mime_type=o.object.mime_type,
            size_bytes=o.object.size_bytes,
            checksum=o.object.checksum,
        )
        for o in outputs
    ]
    return scan_out


# ── POST /scans ──────────────────────────────────────────────────────────
@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def upload_scan(
    request: Request,
    response: Response,
    current_user: CurrentUserDeps,
    audit: AuditLoggerDeps,
    file: UploadFile = File(...),  # noqa: B008
    session: AsyncSession = Depends(get_db),  # noqa: B008
    storage: StorageProvider = Depends(get_storage_provider),  # noqa: B008
    _: None = Depends(enforce_upload_rate_limit),
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
    duplicate = result.get("duplicate", False)
    if duplicate:
        response.status_code = status.HTTP_200_OK
    job = result["job"]
    return envelope(
        data=UploadScanResponse(
            scan=ScanOut.model_validate(result["scan"], from_attributes=True),
            job_id=job.id if job is not None else None,
            job_status=job.status if job is not None else None,
            duplicate=duplicate,
            message="This image has already been uploaded." if duplicate else None,
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
    result = await scan_svc.get_scan(
        session,
        current_user=current_user,
        scan_id=scan_id,
    )
    return envelope(
        data=_with_outputs(
            ScanOut.model_validate(result["scan"], from_attributes=True),
            result["outputs"],
        ),
        trace_id=get_trace_id(request),
    )


# ── GET /scans/{id}/outputs/{type}/url ───────────────────────────────────
@router.get("/{scan_id}/outputs/{output_type}/url")
async def get_output_url(
    request: Request,
    scan_id: UUID,
    output_type: str,
    current_user: CurrentUserDeps,
    audit: AuditLoggerDeps,
    session: AsyncSession = Depends(get_db),  # noqa: B008
    storage: StorageProvider = Depends(get_storage_provider),  # noqa: B008
    _: None = Depends(enforce_download_rate_limit),
) -> dict:
    data = await scan_svc.get_output_url(
        session,
        current_user=current_user,
        storage=storage,
        audit=audit,
        scan_id=scan_id,
        output_type=output_type,
        trace_id=get_trace_id(request),
    )
    return envelope(
        data=ScanOutputUrlOut(**data),
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
