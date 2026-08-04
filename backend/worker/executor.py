"""Job executor — downloads, processes, uploads, persists, and publishes.

`process_message` runs one `inference.run` command end-to-end:

    claim job (QUEUED -> RUNNING) -> download original -> orchestrator.run ->
    upload 4 outputs -> Object + ScanOutput rows -> model_versions row ->
    scan COMPLETED (model_id, noise_variance, processing_time_ms) ->
    job COMPLETED -> publish scan.completed

The orchestrator is the real ML pipeline (ADR-008); this module stays
persistence/transport-only. On any failure the job and scan are marked FAILED
and a `scan.failed` event is published. The executor is idempotent: a message
for an already-terminal job is a no-op.
"""

from __future__ import annotations

import hashlib
import logging
import os
import socket
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
    OUTPUT_TYPE_ENHANCED,
    OUTPUT_TYPE_NOISE_MAP,
    OUTPUT_TYPE_ORIGINAL,
    OUTPUT_TYPE_UNET,
    SCAN_STATUS_COMPLETED,
)
from gateway.repositories.job_repository import JobRepository
from gateway.repositories.object_repository import (
    ObjectRepository,
    ScanOutputRepository,
)
from gateway.repositories.scan_repository import ScanRepository
from worker import orchestrator
from worker.model_manager import ModelManager

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("denoise.worker")

_WORKER_ID = f"{socket.gethostname()}-{os.getpid()}"

_MIME_PNG = "image/png"

_TERMINAL_JOB_STATUSES = (JOB_STATUS_COMPLETED, JOB_STATUS_FAILED, JOB_STATUS_CANCELLED)

# The one ModelManager owned by the worker process (ADR-006). Started by
# worker.main at boot; reused for every job.
model_manager = ModelManager()


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

    original = await storage.download(payload["object_key"])

    result = await orchestrator.run(
        original,
        fmt=fmt,
        model_manager=model_manager,
        original_name=payload["original_name"],
    )
    logger.info(
        "scan %s timings: %s",
        scan_id,
        {k: round(v, 1) for k, v in result.timings.as_dict().items()},
    )

    object_repo = ObjectRepository(session)
    output_repo = ScanOutputRepository(session)

    # ORIGINAL -> link the uploaded object (fills the pre-3.6 gap)
    original_obj = await object_repo.get_by_key(payload["object_key"])
    if original_obj is None:
        raise RuntimeError(f"original object not found for key {payload['object_key']}")
    await output_repo.add(
        scan_id=scan_id, type=OUTPUT_TYPE_ORIGINAL, object_id=original_obj.id
    )

    # NOISE_MAP / UNET / ENHANCED -> upload PNG bytes as new objects
    for output_type, png in (
        (OUTPUT_TYPE_NOISE_MAP, result.noise_map_png),
        (OUTPUT_TYPE_UNET, result.unet_png),
        (OUTPUT_TYPE_ENHANCED, result.enhanced_png),
    ):
        checksum = hashlib.sha256(png).hexdigest()
        output_key = f"outputs/{scan_id}/{uuid.uuid4().hex}/{output_type.lower()}.png"
        stored = await storage.upload(
            output_key, png, content_type=_MIME_PNG, checksum=checksum
        )
        output_object = await object_repo.create(
            bucket=stored.bucket,
            object_key=stored.object_key,
            size_bytes=stored.size_bytes,
            mime_type=stored.mime_type,
            checksum=checksum,
            etag=stored.etag,
        )
        await output_repo.add(
            scan_id=scan_id, type=output_type, object_id=output_object.id
        )

    # Persist model_versions (create or reuse) and link the scan to it
    await model_manager.persist_version(session)

    await scan_repo.set_completed(
        scan_id,
        model_id=model_manager.model_id,
        noise_variance=result.noise_variance,
        processing_time_ms=result.timings.total_ms,
        routing_message=result.routing_message,
        was_bypassed=result.was_bypassed,
        status=SCAN_STATUS_COMPLETED,
    )
    await job_repo.mark_completed(job_id)

    logger.info(
        "scan %s completed in %.1f ms (attempt %d), routing: %s",
        scan_id,
        result.timings.total_ms,
        job.attempt,
        "BYPASS" if result.was_bypassed else "AI",
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
