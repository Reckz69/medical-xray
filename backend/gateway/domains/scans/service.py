"""Scans service — upload, list, get, soft delete.

Upload validation order (never trust Content-Type):
  1. extension
  2. magic bytes
  3. mime
  4. decode
  5. dimensions
  6. size
  7. sha256
  7b. idempotent dedup — same bytes already in this organization? Reuse the
      existing scan (no object upload, no job, no publish); otherwise continue
  8. upload original to object storage
  9. create Object row
  10. create Scan row
  11. create Job row (status QUEUED)
  12. publish `inference.run` command to the commands exchange

All DB mutations run in a single transaction. Users may only read/write their
own scans; anything else raises ForbiddenError.
"""

from __future__ import annotations

import hashlib
import io
import logging
from pathlib import PurePath
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pydicom
from PIL import Image as PILImage
from sqlalchemy.exc import IntegrityError

from gateway.core.config import settings
from gateway.core.errors import (
    ForbiddenError,
    NotFoundError,
    ScanTooLargeError,
    UnsupportedFormatError,
    ValidationError_,
)
from gateway.core.feature_flags import flags
from gateway.core.queue import CMD_INFERENCE_RUN, queue
from gateway.core.storage.base import StorageProvider
from gateway.models.audit import ACTION_DELETE, ACTION_DOWNLOAD, ACTION_UPLOAD
from gateway.models.scan import (
    FORMAT_DICOM,
    FORMAT_JPEG,
    FORMAT_PNG,
    OUTPUT_TYPE_ENHANCED,
    OUTPUT_TYPE_NOISE_MAP,
    OUTPUT_TYPE_ORIGINAL,
    OUTPUT_TYPE_UNET,
    SCAN_STATUS_QUEUED,
    Scan,
)
from gateway.repositories.job_repository import JobRepository
from gateway.repositories.object_repository import (
    ObjectRepository,
    ScanOutputRepository,
)
from gateway.repositories.scan_repository import ScanRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from gateway.core.deps import AuditLogger, CurrentUser
    from gateway.core.storage.base import StorageObject
    from gateway.models.job import Job

logger = logging.getLogger("denoise.scans")

VALID_OUTPUT_TYPES = (
    OUTPUT_TYPE_ORIGINAL,
    OUTPUT_TYPE_NOISE_MAP,
    OUTPUT_TYPE_UNET,
    OUTPUT_TYPE_ENHANCED,
)

ALLOWED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".dcm", ".dicom")

_EXTENSION_TO_FORMAT = {
    ".png": FORMAT_PNG,
    ".jpg": FORMAT_JPEG,
    ".jpeg": FORMAT_JPEG,
    ".dcm": FORMAT_DICOM,
    ".dicom": FORMAT_DICOM,
}

_MIME_BY_FORMAT = {
    FORMAT_PNG: "image/png",
    FORMAT_JPEG: "image/jpeg",
    FORMAT_DICOM: "application/dicom",
}


def _extension_of(filename: str) -> str:
    return PurePath(filename or "").suffix.lower()


def _safe_name(filename: str) -> str:
    return (PurePath(filename or "").name or "upload")[:255]


def _detect_format(data: bytes) -> str | None:
    """Detect the actual image format from magic bytes (never trust Content-Type)."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return FORMAT_PNG
    if data.startswith(b"\xff\xd8\xff"):
        return FORMAT_JPEG
    if len(data) >= 132 and data[128:132] == b"DICM":
        return FORMAT_DICOM
    return None


def _validate_dimensions(width: int, height: int) -> None:
    if width < settings.min_image_dimension or height < settings.min_image_dimension:
        raise ValidationError_(
            f"Image too small ({width}x{height}). Minimum is "
            f"{settings.min_image_dimension}x{settings.min_image_dimension} pixels."
        )
    if width > settings.max_image_dimension or height > settings.max_image_dimension:
        raise ValidationError_(
            f"Image too large ({width}x{height}). Maximum is "
            f"{settings.max_image_dimension}x{settings.max_image_dimension} pixels."
        )


def _decode_dimensions(data: bytes, fmt: str) -> tuple[int, int]:
    """Decode the image and return (width, height). Raises on corrupt payloads."""
    if fmt == FORMAT_DICOM:
        dataset = pydicom.dcmread(io.BytesIO(data), force=False)
        pixel_array = dataset.pixel_array
        height, width = pixel_array.shape[0], pixel_array.shape[1]
        return int(width), int(height)

    image = PILImage.open(io.BytesIO(data))
    image.load()
    return int(image.width), int(image.height)


async def _publish_inference_run(
    *,
    scan: Scan,
    job: Job,
    stored: StorageObject,
    detected_format: str,
    user_id: UUID,
    size_bytes: int,
    content_hash: str,
    trace_id: str,
) -> None:
    """Publish the inference.run command; a broker outage must not fail the upload."""
    payload = {
        "type": CMD_INFERENCE_RUN,
        "scan_id": str(scan.id),
        "job_id": str(job.id),
        "user_id": str(user_id),
        "bucket": stored.bucket,
        "object_key": stored.object_key,
        "format": detected_format,
        "original_name": scan.original_name,
        "size_bytes": size_bytes,
        "checksum": content_hash,
    }
    try:
        await queue.publish_command(CMD_INFERENCE_RUN, payload, trace_id=trace_id)
    except Exception as exc:  # noqa: BLE001 — broker outage must not fail the upload
        logger.warning(
            "failed to publish inference.run for scan %s (job stays QUEUED): %s",
            scan.id,
            exc,
        )


async def upload_scan(
    session: AsyncSession,
    *,
    storage: StorageProvider,
    current_user: CurrentUser,
    audit: AuditLogger,
    filename: str,
    data: bytes,
    trace_id: str = "",
) -> dict:
    """Validate an upload and persist Object + Scan + Job (QUEUED).

    Returns ``{"scan": Scan, "job": Job}`` on success.
    """
    # 1. Extension
    ext = _extension_of(filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise UnsupportedFormatError(
            f"Unsupported file type {ext!r}. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )
    declared_format = _EXTENSION_TO_FORMAT[ext]

    if declared_format == FORMAT_DICOM and not flags.dicom_enabled:
        raise UnsupportedFormatError("DICOM uploads are currently disabled")

    # 2. Magic bytes
    detected_format = _detect_format(data)
    if detected_format is None:
        raise UnsupportedFormatError("File content is not a supported image format")
    if detected_format != declared_format:
        raise UnsupportedFormatError(
            f"File content ({detected_format}) does not match its extension ({ext})"
        )

    # 3. MIME
    mime_type = _MIME_BY_FORMAT[detected_format]

    # 4. Decode
    try:
        width, height = _decode_dimensions(data, detected_format)
    except Exception as exc:
        logger.warning("scan upload rejected: decode failed for %s: %s", filename, exc)
        raise ValidationError_("File is not a valid image") from exc

    # 5. Dimensions
    _validate_dimensions(width, height)

    # 6. Size
    size_bytes = len(data)
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if size_bytes > max_bytes:
        raise ScanTooLargeError(
            f"File too large ({size_bytes / (1024 * 1024):.2f} MB). "
            f"Maximum is {settings.max_upload_size_mb} MB."
        )

    # 7. SHA256
    content_hash = hashlib.sha256(data).hexdigest()

    # 7b. Idempotent dedup: same bytes already in this organization? Reuse the
    # existing scan — no second object, no second job, no second publish.
    scan_repo = ScanRepository(session)
    existing = await scan_repo.get_active_by_org_and_hash(
        current_user.organization_id, content_hash
    )
    if existing is not None:
        logger.info(
            "scan upload dedup: reusing scan %s for hash %s (user %s)",
            existing.id, content_hash[:12], current_user.id,
        )
        return {"scan": existing, "job": None, "duplicate": True}

    # 8. Upload original to object storage
    object_key = f"scans/{current_user.id}/{uuid4().hex}/{_safe_name(filename)}"
    stored = await storage.upload(
        object_key, data, content_type=mime_type, checksum=content_hash
    )

    # 9-11. Object, Scan, Job rows
    object_repo = ObjectRepository(session)
    job_repo = JobRepository(session)

    await object_repo.create(
        bucket=stored.bucket,
        object_key=stored.object_key,
        size_bytes=stored.size_bytes,
        mime_type=stored.mime_type,
        checksum=stored.checksum or content_hash,
        etag=stored.etag,
    )

    scan = await scan_repo.create(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        original_name=filename,
        format=detected_format,
        size_bytes=size_bytes,
        content_hash=content_hash,
        width=width,
        height=height,
        status=SCAN_STATUS_QUEUED,
    )

    job = await job_repo.create(scan_id=scan.id, trace_id=trace_id)

    await audit.log(
        ACTION_UPLOAD,
        user_id=current_user.id,
        organization_id=current_user.organization_id,
        resource_type="scan",
        resource_id=scan.id,
    )

    try:
        await session.commit()
    except IntegrityError:
        # Concurrent duplicate: another request inserted the same bytes first.
        # Roll back and hand back that scan instead of leaking a 500.
        await session.rollback()
        existing = await scan_repo.get_active_by_org_and_hash(
            current_user.organization_id, content_hash
        )
        if existing is not None:
            logger.info(
                "scan upload dedup (race): reusing scan %s for hash %s",
                existing.id, content_hash[:12],
            )
            return {"scan": existing, "job": None, "duplicate": True}
        raise

    await _publish_inference_run(
        scan=scan,
        job=job,
        stored=stored,
        detected_format=detected_format,
        user_id=current_user.id,
        size_bytes=size_bytes,
        content_hash=content_hash,
        trace_id=trace_id,
    )

    logger.info(
        "scan uploaded: %s (%s, %dx%d, %d bytes) by user %s",
        scan.id, detected_format, width, height, size_bytes, current_user.id,
    )

    return {"scan": scan, "job": job}


async def list_scans(
    session: AsyncSession,
    *,
    current_user: CurrentUser,
    offset: int = 0,
    limit: int = 20,
) -> dict:
    """List the current user's scans, newest first."""
    scan_repo = ScanRepository(session)
    items = await scan_repo.list_for_user(current_user.id, limit=limit, offset=offset)
    total = await scan_repo.count_for_user(current_user.id)
    return {"items": items, "total": total, "offset": offset, "limit": limit}


async def get_scan(
    session: AsyncSession,
    *,
    current_user: CurrentUser,
    scan_id: UUID,
) -> dict:
    """Fetch one of the current user's scans (404 if missing/deleted, 403 if foreign).

    Returns ``{"scan": Scan (outputs eager-loaded), "outputs": [ScanOutput, ...]}``.
    """
    scan_repo = ScanRepository(session)
    scan = await scan_repo.get_with_outputs(scan_id)
    if scan is None or scan.deleted_at is not None:
        raise NotFoundError("Scan not found")
    if scan.user_id != current_user.id:
        raise ForbiddenError("You do not have access to this scan")
    return {"scan": scan, "outputs": sorted(scan.outputs, key=lambda o: o.type)}


async def get_output_url(
    session: AsyncSession,
    *,
    current_user: CurrentUser,
    storage: StorageProvider,
    audit: AuditLogger,
    scan_id: UUID,
    output_type: str,
    trace_id: str = "",
) -> dict:
    """Return a short-lived presigned URL for one of the scan's outputs.

    Enforces ownership, validates the output exists, logs a DOWNLOAD audit row,
    and lets the caller's download rate limit gate the request.
    """
    scan_repo = ScanRepository(session)
    scan = await scan_repo.get_by_id(scan_id)
    if scan is None or scan.deleted_at is not None:
        raise NotFoundError("Scan not found")
    if scan.user_id != current_user.id:
        raise ForbiddenError("You do not have access to this scan")

    if output_type not in VALID_OUTPUT_TYPES:
        raise NotFoundError(f"Unknown output type: {output_type}")

    output_repo = ScanOutputRepository(session)
    output = await output_repo.get_for_scan(scan_id, output_type)
    if output is None:
        raise NotFoundError(f"No {output_type} output for this scan")

    obj = await ObjectRepository(session).get_by_id(output.object_id)
    if obj is None:
        raise NotFoundError(f"Object for {output_type} output is missing")

    download_url = await storage.presign_get(obj.object_key)

    await audit.log(
        ACTION_DOWNLOAD,
        user_id=current_user.id,
        organization_id=current_user.organization_id,
        resource_type="scan_output",
        resource_id=output.id,
    )
    await session.commit()

    logger.info(
        "download url issued for scan %s output %s (user %s)",
        scan_id, output_type, current_user.id,
    )

    return {
        "output_type": output_type,
        "download_url": download_url,
        "content_type": obj.mime_type,
        "expires_in": settings.storage_presign_expires_seconds,
    }


async def delete_scan(
    session: AsyncSession,
    *,
    current_user: CurrentUser,
    audit: AuditLogger,
    scan_id: UUID,
) -> None:
    """Soft-delete one of the current user's scans."""
    scan_repo = ScanRepository(session)
    scan = await scan_repo.get_by_id(scan_id)
    if scan is None or scan.deleted_at is not None:
        raise NotFoundError("Scan not found")
    if scan.user_id != current_user.id:
        raise ForbiddenError("You do not have access to this scan")

    await scan_repo.soft_delete(scan.id, deleted_by=current_user.id)
    await audit.log(
        ACTION_DELETE,
        user_id=current_user.id,
        organization_id=current_user.organization_id,
        resource_type="scan",
        resource_id=scan.id,
    )
    await session.commit()

    logger.info("scan soft-deleted: %s by user %s", scan.id, current_user.id)
