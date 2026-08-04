"""Job executor — downloads, processes, uploads, persists, and publishes.

`process_message` runs one `inference.run` command end-to-end:

    claim job (QUEUED -> RUNNING) -> download original -> pipeline.run ->
    upload output -> Object + ScanOutput rows -> scan COMPLETED ->
    job COMPLETED -> publish scan.completed

On any failure the job and scan are marked FAILED and a `scan.failed` event is
published. The executor is idempotent: a message for an already-terminal job is
a no-op.
"""

from __future__ import annotations

import hashlib
import logging
import os
import socket
import time
import uuid
from pathlib import PurePath
from typing import TYPE_CHECKING, Any
from uuid import UUID

from gateway.core.db import SessionLocal
from gateway.core.queue import EVT_SCAN_COMPLETED, EVT_SCAN_FAILED, queue
from gateway.core.storage.factory import storage
from gateway.models.job import (
    JOB_STATUS_CANCELLED,
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
)
from gateway.models.scan import (
    FORMAT_DICOM,
    FORMAT_JPEG,
    FORMAT_PNG,
    OUTPUT_TYPE_ENHANCED,
    SCAN_STATUS_COMPLETED,
)
from gateway.repositories.job_repository import JobRepository
from gateway.repositories.object_repository import (
    ObjectRepository,
    ScanOutputRepository,
)
from gateway.repositories.scan_repository import ScanRepository
from worker import pipeline

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("denoise.worker")

_WORKER_ID = f"{socket.gethostname()}-{os.getpid()}"

_MIME_BY_FORMAT = {
    FORMAT_PNG: "image/png",
    FORMAT_JPEG: "image/jpeg",
    FORMAT_DICOM: "application/dicom",
}

_TERMINAL_JOB_STATUSES = (JOB_STATUS_COMPLETED, JOB_STATUS_FAILED, JOB_STATUS_CANCELLED)


def _safe_name(filename: str) -> str:
    return (PurePath(filename or "").name or "output")[:255]


async def process_message(
    payload: dict[str, Any], *, trace_id: str = "", correlation_id: str = ""
) -> None:
    """Run one inference.run command; the job ends COMPLETED or FAILED."""
    scan_id = UUID(payload["scan_id"])
    job_id = UUID(payload["job_id"])
    try:
        async with SessionLocal() as session:
            changed = await _run_job(session, payload)
            await session.commit()
    except Exception as exc:
        logger.exception("job failed: scan=%s job=%s", scan_id, job_id)
        await _mark_failed(scan_id, job_id, exc)
        await _publish_event(
            EVT_SCAN_FAILED,
            scan_id=scan_id,
            job_id=job_id,
            payload=payload,
            error=exc,
            trace_id=trace_id,
            correlation_id=correlation_id,
        )
        return
    if changed:
        await _publish_event(
            EVT_SCAN_COMPLETED,
            scan_id=scan_id,
            job_id=job_id,
            payload=payload,
            error=None,
            trace_id=trace_id,
            correlation_id=correlation_id,
        )


async def _run_job(session: AsyncSession, payload: dict[str, Any]) -> bool:
    """Execute the job in `session`. Returns False when already terminal."""
    scan_id = UUID(payload["scan_id"])
    job_id = UUID(payload["job_id"])
    fmt = payload["format"]

    job_repo = JobRepository(session)
    scan_repo = ScanRepository(session)

    job = await job_repo.get_by_id(job_id)
    scan = await scan_repo.get_by_id(scan_id)
    if job is None or scan is None:
        raise RuntimeError("job or scan not found")
    if job.status in _TERMINAL_JOB_STATUSES:
        logger.info("job %s already terminal (%s); skipping", job.id, job.status)
        return False

    await job_repo.increment_attempt(job_id)
    await job_repo.claim_started(job_id, worker_id=_WORKER_ID)
    await scan_repo.set_running(scan_id)
    await session.flush()

    started = time.perf_counter()
    original = await storage.download(payload["object_key"])
    output = await pipeline.run(original, fmt=fmt)
    processing_ms = (time.perf_counter() - started) * 1000

    checksum = hashlib.sha256(output).hexdigest()
    output_key = (
        f"outputs/{scan_id}/{uuid.uuid4().hex}/{_safe_name(payload['original_name'])}"
    )
    stored = await storage.upload(
        output_key,
        output,
        content_type=_MIME_BY_FORMAT.get(fmt, "application/octet-stream"),
        checksum=checksum,
    )

    object_repo = ObjectRepository(session)
    output_object = await object_repo.create(
        bucket=stored.bucket,
        object_key=stored.object_key,
        size_bytes=stored.size_bytes,
        mime_type=stored.mime_type,
        checksum=checksum,
        etag=stored.etag,
    )
    await ScanOutputRepository(session).add(
        scan_id=scan_id, type=OUTPUT_TYPE_ENHANCED, object_id=output_object.id
    )
    await scan_repo.set_completed(
        scan_id,
        model_id=None,
        noise_variance=None,
        processing_time_ms=processing_ms,
        status=SCAN_STATUS_COMPLETED,
    )
    await job_repo.mark_completed(job_id)

    logger.info(
        "scan %s completed in %.1f ms (attempt %d)", scan_id, processing_ms, job.attempt
    )
    return True


async def _mark_failed(scan_id: UUID, job_id: UUID, exc: Exception) -> None:
    error = f"{type(exc).__name__}: {exc}"[:2000]
    async with SessionLocal() as session:
        await JobRepository(session).mark_failed(job_id, error=error)
        await ScanRepository(session).set_failed(scan_id, routing_message=error)
        await session.commit()
    logger.error("job %s failed: %s", job_id, error)


async def _publish_event(
    routing_key: str,
    *,
    scan_id: UUID,
    job_id: UUID,
    payload: dict[str, Any],
    error: Exception | None,
    trace_id: str,
    correlation_id: str,
) -> None:
    event = {
        "scan_id": str(scan_id),
        "job_id": str(job_id),
        "status": "FAILED" if routing_key == EVT_SCAN_FAILED else "COMPLETED",
        "format": payload.get("format"),
        "original_name": payload.get("original_name"),
        "object_key": payload.get("object_key"),
        "error": f"{type(error).__name__}: {error}" if error is not None else None,
    }
    try:
        await queue.publish_event(
            routing_key, event, trace_id=trace_id, correlation_id=correlation_id
        )
        logger.info("published %s for scan %s", routing_key, scan_id)
    except Exception as exc:  # noqa: BLE001 — an event broker outage must not crash the worker
        logger.warning("failed to publish %s for scan %s: %s", routing_key, scan_id, exc)
