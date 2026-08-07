"""Scheduler tests — retry state machine, stall recovery, cleanup, idempotency.

Covers (Sprint 4A Phase 1, ADR-009):
  * republish_retries  — due RETRYING jobs re-issue `inference.run` and return
    to QUEUED; not-due jobs are untouched; missing payload terminal-fails.
  * recover_stalled    — stale RUNNING jobs re-enter the retry pipeline, or go
    terminal FAILED (with a scan.failed event) at the attempt cap.
  * recover_unconfirmed — QUEUED republish markers older than the grace window
    are re-issued (scheduler-crash safety).
  * idempotency        — republish is claimed atomically (two passes publish
    once); the worker claim guard rejects a second claim; a terminal job is a
    worker no-op.
  * cleanup            — soft-deleted scans past the retention window are
    purged (rows + S3); recent soft-deletes survive.

These hit the real RabbitMQ/Postgres/MinIO infra; no worker process may be
running while they execute (same contract as test_worker.py).
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import aio_pika
import numpy as np
import pytest
import pytest_asyncio
from aio_pika import ExchangeType
from httpx import AsyncClient
from minio.error import S3Error
from PIL import Image

from gateway.core.config import settings
from gateway.core.db import SessionLocal
from gateway.core.queue import (
    CMD_INFERENCE_RUN,
    COMMANDS_EXCHANGE,
    EVENTS_EXCHANGE,
    EVT_SCAN_FAILED,
)
from gateway.core.redis import redis
from gateway.core.storage.factory import storage
from gateway.models.job import (
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RETRYING,
    JOB_STATUS_RUNNING,
)
from gateway.models.scan import Scan
from gateway.repositories.job_repository import JobRepository
from gateway.repositories.object_repository import (
    ObjectRepository,
    ScanOutputRepository,
)
from gateway.repositories.scan_repository import ScanRepository
from scheduler import cleanup, retry_jobs
from scheduler.cleanup import CLEANUP_LOCK_KEY, CleanupService
from scheduler.consumer import handle_cleanup_run
from scheduler.metrics import metrics
from worker import executor

_PASSWORD = "S3cure!Pass"
_NAME = "Scheduler User"


async def _register(client: AsyncClient, email: str) -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"name": _NAME, "email": email, "password": _PASSWORD},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    return {"token": data["access_token"], "user": data["user"]}


def _png_bytes(size: tuple[int, int] = (256, 256)) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(
        np.random.randint(0, 256, (size[1], size[0]), dtype=np.uint8),
        mode="L",
    ).save(buf, format="PNG")
    return buf.getvalue()


async def _upload(client: AsyncClient, token: str, filename: str, content: bytes) -> dict:
    resp = await client.post(
        "/api/v1/scans",
        files={"file": (filename, content, "image/png")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 202, resp.text
    return resp.json()["data"]


class _QueueReader:
    def __init__(self, connection: Any, channel: Any, queue: Any) -> None:
        self.connection = connection
        self.channel = channel
        self.queue = queue

    async def read_one(self, timeout: float = 2.0) -> tuple[dict, dict]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            message = await self.queue.get(fail=False)
            if message is not None:
                await message.ack()
                return json.loads(message.body), message.headers or {}
            await asyncio.sleep(0.05)
        raise TimeoutError("no message received")

    async def read_for(self, job_id: str, *, timeout: float = 3.0) -> tuple[dict, dict]:
        """Read the next message whose payload matches `job_id`, skipping others.

        The dev DB is shared, so earlier runs can leave jobs that the scheduler
        legitimately republishes during this test; those messages are consumed
        and discarded (the worker queue still receives them).
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            message = await self.queue.get(fail=False)
            if message is None:
                await asyncio.sleep(0.05)
                continue
            await message.ack()
            body = json.loads(message.body)
            if body.get("job_id") == job_id:
                return body, message.headers or {}
        raise TimeoutError(f"no message for job {job_id}")

    async def close(self) -> None:
        with contextlib.suppress(Exception):
            await self.queue.delete()
        with contextlib.suppress(Exception):
            await self.connection.close()


async def _bind_reader(exchange_name: str, routing_key: str) -> _QueueReader:
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await connection.channel()
    exchange = await channel.declare_exchange(
        exchange_name, ExchangeType.TOPIC, durable=True
    )
    queue = await channel.declare_queue(
        f"test.{uuid.uuid4().hex}", durable=False, auto_delete=True
    )
    await queue.bind(exchange, routing_key)
    return _QueueReader(connection, channel, queue)


@pytest_asyncio.fixture
async def commands_reader() -> Any:
    reader = await _bind_reader(COMMANDS_EXCHANGE, CMD_INFERENCE_RUN)
    yield reader
    await reader.close()


@pytest_asyncio.fixture
async def failed_events_reader() -> Any:
    reader = await _bind_reader(EVENTS_EXCHANGE, EVT_SCAN_FAILED)
    yield reader
    await reader.close()


async def _uploaded_job(client: AsyncClient) -> tuple[str, str, str]:
    """Register + upload a fresh scan; returns (scan_id, job_id, token)."""
    email = f"sched_{uuid.uuid4().hex[:8]}@example.com"
    token = (await _register(client, email))["token"]
    data = await _upload(client, token, "chest.png", _png_bytes())
    return data["scan"]["id"], data["job_id"], token


# ═══════════════════════════════════════════════════════════════════════════
# republish_retries — the retry state machine
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_due_retry_is_republished_and_requeued(
    client: AsyncClient, commands_reader: Any
) -> None:
    scan_id, job_id, _ = await _uploaded_job(client)
    now = datetime.now(UTC)

    await commands_reader.read_for(job_id)  # drain the upload's original command

    async with SessionLocal() as session:
        await JobRepository(session).mark_retrying(
            uuid.UUID(job_id),
            next_retry_at=now - timedelta(seconds=1),
            error="transient failure",
        )
        await session.commit()

    async with SessionLocal() as session:
        count = await retry_jobs.republish_retries(session, now=now)
        await session.commit()
    assert count == 1

    cmd, _ = await commands_reader.read_for(job_id)
    assert cmd["scan_id"] == scan_id

    async with SessionLocal() as session:
        job = await JobRepository(session).get_by_id(uuid.UUID(job_id))
        assert job is not None
        assert job.status == JOB_STATUS_QUEUED
        assert job.next_retry_at is None


@pytest.mark.asyncio
async def test_retry_not_due_is_not_published(client: AsyncClient) -> None:
    _, job_id, _ = await _uploaded_job(client)
    now = datetime.now(UTC)

    async with SessionLocal() as session:
        await JobRepository(session).mark_retrying(
            uuid.UUID(job_id),
            next_retry_at=now + timedelta(hours=1),
        )
        await session.commit()

    async with SessionLocal() as session:
        count = await retry_jobs.republish_retries(session, now=now)
        await session.commit()
    assert count == 0

    async with SessionLocal() as session:
        job = await JobRepository(session).get_by_id(uuid.UUID(job_id))
        assert job is not None
        assert job.status == JOB_STATUS_RETRYING


@pytest.mark.asyncio
async def test_retry_with_missing_payload_marks_failed(
    client: AsyncClient, commands_reader: Any
) -> None:
    _, job_id, _ = await _uploaded_job(client)
    now = datetime.now(UTC)

    await commands_reader.read_for(job_id)  # drain the upload's original command

    async with SessionLocal() as session:
        await JobRepository(session).mark_retrying(
            uuid.UUID(job_id),
            next_retry_at=now - timedelta(seconds=1),
        )
        job = await JobRepository(session).get_by_id(uuid.UUID(job_id))
        job.payload = None
        await session.commit()

    async with SessionLocal() as session:
        count = await retry_jobs.republish_retries(session, now=now)
        await session.commit()
    assert count == 1

    with pytest.raises(TimeoutError):
        await commands_reader.read_for(job_id, timeout=1.0)

    async with SessionLocal() as session:
        job = await JobRepository(session).get_by_id(uuid.UUID(job_id))
        assert job is not None
        assert job.status == JOB_STATUS_FAILED
        assert "payload" in job.error


# ═══════════════════════════════════════════════════════════════════════════
# recover_stalled — stale RUNNING jobs (worker lost)
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_stalled_running_job_reenters_retry_pipeline(client: AsyncClient) -> None:
    scan_id, job_id, _ = await _uploaded_job(client)
    now = datetime.now(UTC)

    async with SessionLocal() as session:
        job = await JobRepository(session).get_by_id(uuid.UUID(job_id))
        job.status = JOB_STATUS_RUNNING
        job.attempt = 1
        job.started_at = now - timedelta(seconds=settings.job_stall_timeout_seconds + 10)
        await session.commit()

    async with SessionLocal() as session:
        count = await retry_jobs.recover_stalled(session, now=now)
        await session.commit()
    assert count == 1

    async with SessionLocal() as session:
        job = await JobRepository(session).get_by_id(uuid.UUID(job_id))
        assert job.status == JOB_STATUS_RETRYING
        expected = now + timedelta(seconds=retry_jobs.backoff_seconds(1))
        assert abs((job.next_retry_at - expected).total_seconds()) < 5

    # Once the backoff elapses the republish pass actually re-issues the job.
    later = now + timedelta(seconds=retry_jobs.backoff_seconds(1) + 1)
    async with SessionLocal() as session:
        count = await retry_jobs.republish_retries(session, now=later)
        await session.commit()
    assert count == 1
    async with SessionLocal() as session:
        job = await JobRepository(session).get_by_id(uuid.UUID(job_id))
        assert job.status == JOB_STATUS_QUEUED
    assert scan_id  # silence unused-variable warnings on the read


@pytest.mark.asyncio
async def test_stalled_running_at_attempt_cap_marks_failed(
    client: AsyncClient, failed_events_reader: Any
) -> None:
    scan_id, job_id, _ = await _uploaded_job(client)
    now = datetime.now(UTC)

    async with SessionLocal() as session:
        job = await JobRepository(session).get_by_id(uuid.UUID(job_id))
        job.status = JOB_STATUS_RUNNING
        job.attempt = 3
        job.max_attempts = 3
        job.started_at = now - timedelta(seconds=settings.job_stall_timeout_seconds + 10)
        await session.commit()

    async with SessionLocal() as session:
        count = await retry_jobs.recover_stalled(session, now=now)
        await session.commit()
    assert count == 0  # recovered-count only counts re-entering the pipeline

    event, _ = await failed_events_reader.read_for(job_id)
    assert event["scan_id"] == scan_id
    assert event["status"] == "FAILED"

    async with SessionLocal() as session:
        job = await JobRepository(session).get_by_id(uuid.UUID(job_id))
        assert job.status == JOB_STATUS_FAILED
        assert "stalled" in job.error
        scan = await ScanRepository(session).get_by_id(uuid.UUID(scan_id))
        assert scan is not None
        assert scan.status == "FAILED"


# ═══════════════════════════════════════════════════════════════════════════
# recover_unconfirmed — scheduler-crash safety
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_unconfirmed_queued_retry_is_republished(
    client: AsyncClient, commands_reader: Any
) -> None:
    scan_id, job_id, _ = await _uploaded_job(client)
    now = datetime.now(UTC)

    await commands_reader.read_for(job_id)  # drain the upload's original command

    # Simulate: claim_republish ran (QUEUED + marker) but confirm never did.
    async with SessionLocal() as session:
        job = await JobRepository(session).get_by_id(uuid.UUID(job_id))
        job.status = JOB_STATUS_QUEUED
        job.attempt = 1
        job.next_retry_at = now - timedelta(hours=1)
        await session.commit()

    async with SessionLocal() as session:
        count = await retry_jobs.recover_unconfirmed(session, now=now)
        await session.commit()
    assert count == 1

    cmd, _ = await commands_reader.read_for(job_id)
    assert cmd["scan_id"] == scan_id

    async with SessionLocal() as session:
        job = await JobRepository(session).get_by_id(uuid.UUID(job_id))
        assert job.status == JOB_STATUS_QUEUED
        assert job.next_retry_at is None


# ═══════════════════════════════════════════════════════════════════════════
# Idempotency — atomic claims + terminal no-op
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_republish_claims_atomically_once(client: AsyncClient, commands_reader: Any) -> None:
    scan_id, job_id, _ = await _uploaded_job(client)
    now = datetime.now(UTC)

    await commands_reader.read_for(job_id)  # drain the upload's original command

    async with SessionLocal() as session:
        await JobRepository(session).mark_retrying(
            uuid.UUID(job_id),
            next_retry_at=now - timedelta(seconds=1),
        )
        await session.commit()

    # Two consecutive passes must publish exactly once.
    async with SessionLocal() as session:
        first = await retry_jobs.republish_retries(session, now=now)
        await session.commit()
    async with SessionLocal() as session:
        second = await retry_jobs.republish_retries(session, now=now)
        await session.commit()
    assert first == 1
    assert second == 0

    cmd, _ = await commands_reader.read_for(job_id)
    assert cmd["scan_id"] == scan_id
    with pytest.raises(TimeoutError):
        await commands_reader.read_for(job_id, timeout=1.0)


@pytest.mark.asyncio
async def test_worker_claim_guard_rejects_second_claim(client: AsyncClient) -> None:
    _, job_id, _ = await _uploaded_job(client)

    async with SessionLocal() as session:
        repo = JobRepository(session)
        first = await repo.claim_for_execution(uuid.UUID(job_id), worker_id="w1")
        second = await repo.claim_for_execution(uuid.UUID(job_id), worker_id="w2")
        assert first is True
        assert second is False
        job = await repo.get_by_id(uuid.UUID(job_id))
        assert job.status == JOB_STATUS_RUNNING
        assert job.attempt == 1
        assert job.worker_id == "w1"


@pytest.mark.asyncio
async def test_worker_skips_terminal_job_without_processing(
    client: AsyncClient, commands_reader: Any
) -> None:
    scan_id, job_id, _ = await _uploaded_job(client)

    cmd, _ = await commands_reader.read_for(job_id)
    assert cmd["scan_id"] == scan_id

    # The job completes elsewhere before this (duplicate) command arrives.
    async with SessionLocal() as session:
        await JobRepository(session).mark_completed(uuid.UUID(job_id))
        await session.commit()

    await executor.process_message(cmd)

    async with SessionLocal() as session:
        job = await JobRepository(session).get_by_id(uuid.UUID(job_id))
        assert job.status == JOB_STATUS_COMPLETED
        assert job.attempt == 0  # never re-claimed
        outputs = await ScanOutputRepository(session).list_for_scan(uuid.UUID(scan_id))
        assert outputs == []


# ═══════════════════════════════════════════════════════════════════════════
# Cleanup — purge soft-deleted scans after the retention window
# ═══════════════════════════════════════════════════════════════════════════
async def _deleted_scan_with_outputs(client: AsyncClient) -> tuple[str, str, dict, dict]:
    """Upload, simulate a completed scan (4 outputs + objects), soft-delete it.

    Returns (scan_id, job_id, token, {output_type: object_key}).
    """
    scan_id, job_id, token = await _uploaded_job(client)
    keys: dict[str, str] = {}

    async with SessionLocal() as session:
        job_repo = JobRepository(session)
        job = await job_repo.get_by_id(uuid.UUID(job_id))
        object_repo = ObjectRepository(session)
        output_repo = ScanOutputRepository(session)
        original = await object_repo.get_by_key(job.payload["object_key"])
        assert original is not None
        await output_repo.add(
            scan_id=uuid.UUID(scan_id), type="ORIGINAL", object_id=original.id
        )
        keys["ORIGINAL"] = original.object_key

        for out_type in ("NOISE_MAP", "UNET", "ENHANCED"):
            key = f"outputs/{scan_id}/test/{uuid.uuid4().hex}/{out_type.lower()}.png"
            stored = await storage.upload(key, _png_bytes(), content_type="image/png")
            obj = await object_repo.create(
                bucket=stored.bucket,
                object_key=stored.object_key,
                size_bytes=stored.size_bytes,
                mime_type=stored.mime_type,
                checksum="test",
            )
            await output_repo.add(
                scan_id=uuid.UUID(scan_id), type=out_type, object_id=obj.id
            )
            keys[out_type] = stored.object_key
        await session.commit()

    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.delete(f"/api/v1/scans/{scan_id}", headers=headers)
    assert resp.status_code == 204, resp.text
    return scan_id, job_id, token, keys


@pytest.mark.asyncio
async def test_purge_removes_scan_rows_and_objects(client: AsyncClient) -> None:
    scan_id, _job_id, _, keys = await _deleted_scan_with_outputs(client)
    now = datetime.now(UTC)

    # Age the soft-delete beyond the retention window.
    async with SessionLocal() as session:
        scan = await session.get(Scan, uuid.UUID(scan_id))
        scan.deleted_at = now - timedelta(days=settings.scan_purge_days + 1)
        await session.commit()

    async with SessionLocal() as session:
        purged = await cleanup.purge_soft_deleted(session, now=now)
        await session.commit()
    assert purged == 1

    # Every key must be gone from storage.
    for key in keys.values():
        with pytest.raises(S3Error):
            await storage.download(key)

    async with SessionLocal() as session:
        assert await session.get(Scan, uuid.UUID(scan_id)) is None
        assert await JobRepository(session).get_by_scan_id(uuid.UUID(scan_id)) is None
        assert await ScanOutputRepository(session).list_for_scan(uuid.UUID(scan_id)) == []


@pytest.mark.asyncio
async def test_purge_skips_recently_deleted_scan(client: AsyncClient) -> None:
    scan_id, _, _, _ = await _deleted_scan_with_outputs(client)
    now = datetime.now(UTC)

    async with SessionLocal() as session:
        purged = await cleanup.purge_soft_deleted(session, now=now)
        await session.commit()
    assert purged == 0

    async with SessionLocal() as session:
        scan = await session.get(Scan, uuid.UUID(scan_id))
        assert scan is not None
        assert scan.deleted_at is not None


# ═══════════════════════════════════════════════════════════════════════════
# Metrics
# ═══════════════════════════════════════════════════════════════════════════
def test_metrics_snapshot_shape() -> None:
    snap = metrics.snapshot()
    for key in (
        "last_run_at",
        "cycles",
        "jobs_republished",
        "jobs_recovered",
        "jobs_failed_terminal",
        "jobs_payload_missing",
        "scans_purged",
        "objects_purged",
        "objects_archived",
        "cleanup_duration_seconds",
        "cleanup_failures",
        "cleanup_skipped_runs",
        "last_error",
    ):
        assert key in snap


# ═══════════════════════════════════════════════════════════════════════════
# CleanupService — single implementation, distributed lock, metrics, sources
# ═══════════════════════════════════════════════════════════════════════════
async def _age_soft_deleted(scan_id: str, *, days: int | None = None) -> None:
    """Backdate a soft-deleted scan past the retention window."""
    age = days if days is not None else settings.scan_purge_days + 1
    async with SessionLocal() as session:
        scan = await session.get(Scan, uuid.UUID(scan_id))
        assert scan is not None
        scan.deleted_at = datetime.now(UTC) - timedelta(days=age)
        await session.commit()


@pytest.mark.asyncio
async def test_cleanup_service_run_reports_timer_source(client: AsyncClient) -> None:
    scan_id, _, _, _ = await _deleted_scan_with_outputs(client)
    await _age_soft_deleted(scan_id)

    service = CleanupService()
    result = await service.run_cleanup(source="timer")

    assert result["source"] == "timer"
    assert result["skipped"] is False
    assert result["purged"] >= 1
    assert result["duration_seconds"] is not None
    assert metrics.scans_purged >= 1
    assert metrics.cleanup_duration_seconds is not None

    async with SessionLocal() as session:
        assert await session.get(Scan, uuid.UUID(scan_id)) is None


@pytest.mark.asyncio
async def test_cleanup_service_skips_when_lock_held(client: AsyncClient) -> None:
    scan_id, _, _, _ = await _deleted_scan_with_outputs(client)
    await _age_soft_deleted(scan_id)

    await redis.delete(CLEANUP_LOCK_KEY)
    before = metrics.cleanup_skipped_runs
    service = CleanupService()
    # Simulate a concurrent scheduler holding the distributed lock.
    await redis.set(CLEANUP_LOCK_KEY, "other-owner", nx=True, px=60_000)
    try:
        result = await service.run_cleanup(source="timer")
    finally:
        await redis.delete(CLEANUP_LOCK_KEY)

    assert result["skipped"] is True
    assert result["reason"] == "lock_held"
    assert result["purged"] == 0
    assert metrics.cleanup_skipped_runs == before + 1

    # The aged scan survives — no concurrent purge while the lock is held.
    async with SessionLocal() as session:
        assert await session.get(Scan, uuid.UUID(scan_id)) is not None

    # Purge the aged scan so it can't leak into later cleanup runs.
    await service.run_cleanup(source="timer")


@pytest.mark.asyncio
async def test_cleanup_service_releases_lock_after_run(client: AsyncClient) -> None:
    scan_id, _, _, _ = await _deleted_scan_with_outputs(client)
    await _age_soft_deleted(scan_id)

    await redis.delete(CLEANUP_LOCK_KEY)
    service = CleanupService()

    first = await service.run_cleanup(source="timer")
    assert first["skipped"] is False
    assert first["purged"] >= 1

    # The lock was released, so a follow-up run is not skipped.
    second = await service.run_cleanup(source="timer")
    assert second["skipped"] is False
    assert await redis.get(CLEANUP_LOCK_KEY) is None


@pytest.mark.asyncio
async def test_cleanup_run_command_uses_cleanup_source() -> None:
    class _FakeService:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def run_cleanup(self, *, source: str, now=None) -> dict:
            self.calls.append(source)
            return {"source": source, "purged": 0, "skipped": False}

    fake = _FakeService()
    result = await handle_cleanup_run({}, service=fake)

    assert fake.calls == ["cleanup.run"]
    assert result["source"] == "cleanup.run"
