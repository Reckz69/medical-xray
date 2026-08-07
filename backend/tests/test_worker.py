"""Worker integration tests (Sprint 3.6 async processing).

Covers the full loop: upload -> gateway publishes `inference.run` to the
commands exchange -> worker consumes and executes -> `scan.completed` event
published -> job/scan COMPLETED, four scan_output rows (ORIGINAL / NOISE_MAP /
UNET / ENHANCED), a model_versions row, scan.model_id/noise_variance/
processing_time_ms persisted, output objects in MinIO. Also covers the FAILED
path (orchestrator raises).

These tests hit the real RabbitMQ/Postgres/MinIO infra, so no worker process
may be running concurrently while they execute.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import uuid
from typing import Any

import aio_pika
import numpy as np
import pytest
import pytest_asyncio
from aio_pika import ExchangeType
from httpx import AsyncClient
from PIL import Image

from gateway.core.config import settings
from gateway.core.db import SessionLocal
from gateway.core.queue import (
    CMD_INFERENCE_RUN,
    COMMANDS_EXCHANGE,
    EVENTS_EXCHANGE,
    EVT_SCAN_COMPLETED,
    EVT_SCAN_FAILED,
)
from gateway.core.storage.factory import storage
from gateway.models.scan import (
    OUTPUT_TYPE_ENHANCED,
    OUTPUT_TYPE_NOISE_MAP,
    OUTPUT_TYPE_ORIGINAL,
    OUTPUT_TYPE_UNET,
)
from gateway.repositories.job_repository import JobRepository
from gateway.repositories.model_repository import ModelVersionRepository
from gateway.repositories.object_repository import (
    ObjectRepository,
    ScanOutputRepository,
)
from gateway.repositories.scan_repository import ScanRepository
from worker import orchestrator
from worker.consumer import handle_inference_run

_PASSWORD = "S3cure!Pass"
_NAME = "Worker User"


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


async def _upload(
    client: AsyncClient, token: str, filename: str, content: bytes
) -> Any:
    return await client.post(
        "/api/v1/scans",
        files={"file": (filename, content, "image/png")},
        headers={"Authorization": f"Bearer {token}"},
    )


class _QueueReader:
    def __init__(self, connection: Any, channel: Any, queue: Any) -> None:
        self.connection = connection
        self.channel = channel
        self.queue = queue

    async def read_one(self, timeout: float = 5.0) -> tuple[dict, dict]:
        async with asyncio.timeout(timeout):
            async with self.queue.iterator() as iterator:
                async for message in iterator:
                    await message.ack()
                    return json.loads(message.body), message.headers or {}
        raise AssertionError("timed out waiting for a message")

    async def close(self) -> None:
        await self.queue.delete()
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
async def completed_events_reader() -> Any:
    reader = await _bind_reader(EVENTS_EXCHANGE, EVT_SCAN_COMPLETED)
    yield reader
    await reader.close()


@pytest_asyncio.fixture
async def failed_events_reader() -> Any:
    reader = await _bind_reader(EVENTS_EXCHANGE, EVT_SCAN_FAILED)
    yield reader
    await reader.close()


# ═══════════════════════════════════════════════════════════════════════════
# Happy path: upload -> command -> worker -> completed
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_upload_runs_worker_to_completed(
    client: AsyncClient,
    commands_reader: Any,
    completed_events_reader: Any,
) -> None:
    email = f"worker_ok_{uuid.uuid4().hex[:8]}@example.com"
    token = (await _register(client, email))["token"]
    content = _png_bytes()

    resp = await _upload(client, token, "chest.png", content)
    assert resp.status_code == 202, resp.text
    data = resp.json()["data"]
    scan_id = data["scan"]["id"]
    job_id = data["job_id"]
    assert data["job_status"] == "QUEUED"

    # 1. The gateway published inference.run to the commands exchange
    cmd, headers = await commands_reader.read_one()
    assert cmd["scan_id"] == scan_id
    assert cmd["job_id"] == job_id
    assert cmd["object_key"]
    assert cmd["bucket"] == settings.s3_bucket
    assert headers.get("trace_id", "") != ""

    # 2. Worker consumes the command and executes the job
    await handle_inference_run(cmd, trace_id=headers.get("trace_id", ""))

    # 3. scan.completed event was published to the events exchange
    event, _ = await completed_events_reader.read_one()
    assert event["scan_id"] == scan_id
    assert event["job_id"] == job_id
    assert event["status"] == "COMPLETED"

    # 4. DB: job + scan COMPLETED with full pipeline metadata
    async with SessionLocal() as session:
        job = await JobRepository(session).get_by_id(uuid.UUID(job_id))
        assert job is not None
        assert job.status == "COMPLETED"
        assert job.attempt == 1
        assert job.worker_id
        assert job.finished_at is not None

        scan = await ScanRepository(session).get_by_id(uuid.UUID(scan_id))
        assert scan is not None
        assert scan.status == "COMPLETED"
        assert scan.completed_at is not None
        assert scan.processing_time_ms is not None
        assert scan.noise_variance is not None
        assert scan.routing_message and "PATH" in scan.routing_message
        assert scan.was_bypassed == ("PATH B" in scan.routing_message)

        model_version = await ModelVersionRepository(session).get_by_id(scan.model_id)
        assert model_version is not None
        assert model_version.model_name == settings.model_name
        assert model_version.model_version == settings.model_version

        # 5. All four scan_output rows exist, each with its own object
        outputs = {
            out_type: await ScanOutputRepository(session).get_for_scan(
                uuid.UUID(scan_id), out_type
            )
            for out_type in (
                OUTPUT_TYPE_ORIGINAL,
                OUTPUT_TYPE_NOISE_MAP,
                OUTPUT_TYPE_UNET,
                OUTPUT_TYPE_ENHANCED,
            )
        }
        for out_type, output in outputs.items():
            assert output is not None, f"missing scan_output {out_type}"
            obj = await ObjectRepository(session).get_by_id(output.object_id)
            assert obj is not None, f"missing object for {out_type}"

        # 6. ORIGINAL links the uploaded object (identity, same checksum)
        original_object = await ObjectRepository(session).get_by_id(
            outputs[OUTPUT_TYPE_ORIGINAL].object_id
        )
        assert original_object.object_key == cmd["object_key"]
        assert original_object.checksum == hashlib.sha256(content).hexdigest()

        # 7. Derived outputs in MinIO, checksums match stored bytes
        for out_type in (
            OUTPUT_TYPE_NOISE_MAP,
            OUTPUT_TYPE_UNET,
            OUTPUT_TYPE_ENHANCED,
        ):
            output_object = await ObjectRepository(session).get_by_id(
                outputs[out_type].object_id
            )
            assert output_object.object_key != cmd["object_key"]
            stored_bytes = await storage.download(output_object.object_key)
            assert hashlib.sha256(stored_bytes).hexdigest() == output_object.checksum


# ═══════════════════════════════════════════════════════════════════════════
# Failure path: pipeline raises -> RETRYING (attempt < cap), then terminal
# FAILED with scan.failed published once attempts are exhausted (ADR-009).
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_worker_failure_marks_job_and_scan_failed(
    client: AsyncClient,
    commands_reader: Any,
    failed_events_reader: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _boom(
        data: bytes,
        *,
        fmt: str,
        model_manager: Any,
        original_name: str = "",
        **kwargs: Any,
    ) -> bytes:
        raise RuntimeError("model exploded")

    monkeypatch.setattr(orchestrator, "run", _boom)

    email = f"worker_fail_{uuid.uuid4().hex[:8]}@example.com"
    token = (await _register(client, email))["token"]

    resp = await _upload(client, token, "chest.png", _png_bytes())
    assert resp.status_code == 202, resp.text
    data = resp.json()["data"]
    scan_id = data["scan"]["id"]
    job_id = data["job_id"]

    cmd, headers = await commands_reader.read_one()
    assert cmd["scan_id"] == scan_id

    # 1. First failure (attempt 1 of 3) is retryable: RETRYING, no event yet.
    await handle_inference_run(cmd, trace_id=headers.get("trace_id", ""))
    async with SessionLocal() as session:
        job = await JobRepository(session).get_by_id(uuid.UUID(job_id))
        assert job is not None
        assert job.status == "RETRYING"
        assert job.attempt == 1
        assert job.next_retry_at is not None
        assert "model exploded" in job.error

    # 2. Simulate the scheduler requeueing the retry and exhaust the cap.
    async with SessionLocal() as session:
        job = await JobRepository(session).get_by_id(uuid.UUID(job_id))
        job.status = "QUEUED"
        job.attempt = job.max_attempts - 1
        await session.commit()

    await handle_inference_run(cmd, trace_id=headers.get("trace_id", ""))

    event, _ = await failed_events_reader.read_one()
    assert event["scan_id"] == scan_id
    assert event["job_id"] == job_id
    assert event["status"] == "FAILED"
    assert "model exploded" in event["error"]

    async with SessionLocal() as session:
        job = await JobRepository(session).get_by_id(uuid.UUID(job_id))
        assert job is not None
        assert job.status == "FAILED"
        assert "model exploded" in job.error
        assert job.finished_at is not None

        scan = await ScanRepository(session).get_by_id(uuid.UUID(scan_id))
        assert scan is not None
        assert scan.status == "FAILED"
        assert scan.routing_message
