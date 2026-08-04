"""Scan output metadata + presigned download URL tests.

Covers:
  - GET /api/v1/scans/{id} returns output metadata for a completed scan
    (type / mime / size / checksum — never an automatically-issued URL).
  - GET /api/v1/scans/{id}/outputs/{type}/url issues a short-lived presigned
    URL, writes an audit DOWNLOAD row, and enforces download rate limits.
  - Ownership + auth + 404 semantics.

Requires the real RabbitMQ/Postgres/MinIO infra; the worker executor runs
in-process via `handle_inference_run` (no worker process running).
"""

from __future__ import annotations

import asyncio
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
)
from gateway.repositories.audit_repository import AuditLogRepository
from worker.consumer import handle_inference_run

_PASSWORD = "S3cure!Pass"
_NAME = "Outputs User"

OUTPUT_TYPES = ("ORIGINAL", "NOISE_MAP", "UNET", "ENHANCED")


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


async def _upload(client: AsyncClient, token: str, filename: str, content: bytes):
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


async def _completed_scan(
    client: AsyncClient, commands_reader: Any
) -> tuple[str, str, str]:
    """Upload + run the worker once; returns (scan_id, job_id, token)."""
    email = f"out_{uuid.uuid4().hex[:8]}@example.com"
    token = (await _register(client, email))["token"]

    resp = await _upload(client, token, "chest.png", _png_bytes())
    assert resp.status_code == 202, resp.text
    data = resp.json()["data"]
    scan_id = data["scan"]["id"]
    job_id = data["job_id"]

    cmd, headers = await commands_reader.read_one()
    assert cmd["scan_id"] == scan_id
    await handle_inference_run(cmd, trace_id=headers.get("trace_id", ""))
    return scan_id, job_id, token


# ═══════════════════════════════════════════════════════════════════════════
# GET /scans/{id} output metadata
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_get_scan_includes_output_metadata(
    client: AsyncClient, commands_reader: Any
) -> None:
    scan_id, _, token = await _completed_scan(client, commands_reader)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get(f"/api/v1/scans/{scan_id}", headers=headers)
    assert resp.status_code == 200
    body = resp.json()["data"]

    assert body["status"] == "COMPLETED"
    assert body["processing_time_ms"] is not None
    assert body["noise_variance"] is not None
    assert body["routing_message"]
    assert body["was_bypassed"] in (True, False)
    assert body["model_id"]

    # No presigned URL is auto-issued; metadata only.
    types = {o["type"] for o in body["outputs"]}
    assert types == set(OUTPUT_TYPES), body["outputs"]
    for out in body["outputs"]:
        assert out["mime_type"]
        assert out["size_bytes"] > 0
        assert out["checksum"]
        assert "url" not in out


@pytest.mark.asyncio
async def test_get_queued_scan_has_empty_outputs(client: AsyncClient) -> None:
    email = f"out_q_{uuid.uuid4().hex[:8]}@example.com"
    token = (await _register(client, email))["token"]

    upload = await _upload(client, token, "chest.png", _png_bytes())
    scan_id = upload.json()["data"]["scan"]["id"]

    resp = await client.get(
        f"/api/v1/scans/{scan_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "QUEUED"
    assert resp.json()["data"]["outputs"] == []


# ═══════════════════════════════════════════════════════════════════════════
# GET /scans/{id}/outputs/{type}/url
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_output_url_returns_presigned_url_and_audits(
    client: AsyncClient, commands_reader: Any
) -> None:
    scan_id, _, token = await _completed_scan(client, commands_reader)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get(
        f"/api/v1/scans/{scan_id}/outputs/ENHANCED/url",
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["output_type"] == "ENHANCED"
    assert body["download_url"].startswith("http")
    assert "X-Amz-Signature" in body["download_url"]
    assert body["content_type"] == "image/png"
    assert body["expires_in"] == settings.storage_presign_expires_seconds

    # DOWNLOAD audit row written
    user = (await client.get("/api/v1/auth/me", headers=headers)).json()["data"]
    async with SessionLocal() as session:
        rows = await AuditLogRepository(session).list_for_user(user["id"])
        assert any(
            r.action == "DOWNLOAD"
            and r.resource_type == "scan_output"
            for r in rows
        ), rows


@pytest.mark.asyncio
async def test_output_url_for_original_output(client: AsyncClient, commands_reader: Any) -> None:
    scan_id, _, token = await _completed_scan(client, commands_reader)
    resp = await client.get(
        f"/api/v1/scans/{scan_id}/outputs/ORIGINAL/url",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["output_type"] == "ORIGINAL"


@pytest.mark.asyncio
async def test_output_url_unknown_type_404(client: AsyncClient, commands_reader: Any) -> None:
    scan_id, _, token = await _completed_scan(client, commands_reader)
    resp = await client.get(
        f"/api/v1/scans/{scan_id}/outputs/SUPER_RES/url",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_output_url_missing_output_404(client: AsyncClient) -> None:
    email = f"out_m_{uuid.uuid4().hex[:8]}@example.com"
    token = (await _register(client, email))["token"]
    upload = await _upload(client, token, "chest.png", _png_bytes())
    scan_id = upload.json()["data"]["scan"]["id"]

    # QUEUED scan has no outputs yet
    resp = await client.get(
        f"/api/v1/scans/{scan_id}/outputs/ENHANCED/url",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_output_url_foreign_scan_403(
    client: AsyncClient, commands_reader: Any
) -> None:
    scan_id, _, _ = await _completed_scan(client, commands_reader)
    email_b = f"out_b_{uuid.uuid4().hex[:8]}@example.com"
    token_b = (await _register(client, email_b))["token"]

    resp = await client.get(
        f"/api/v1/scans/{scan_id}/outputs/ENHANCED/url",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_output_url_requires_auth(client: AsyncClient, commands_reader: Any) -> None:
    scan_id, _, _ = await _completed_scan(client, commands_reader)
    resp = await client.get(f"/api/v1/scans/{scan_id}/outputs/ENHANCED/url")
    assert resp.status_code == 401
    assert resp.json()["code"] == "UNAUTHORIZED"


# ═══════════════════════════════════════════════════════════════════════════
# Rate limits (upload + download)
#
# The conftest autouse fixture bypasses Redis rate limiting entirely, so these
# tests inject a deterministic limiter scoped to the `upload:`/`download:` keys
# (register/login stay bypassed). This verifies the endpoint wiring (429 +
# Retry-After); the Redis fixed-window math lives in core/rate_limit.py.
# ═══════════════════════════════════════════════════════════════════════════
def _fake_limiter(monkeypatch: pytest.MonkeyPatch, *, limit: int = 2) -> None:
    import time

    import gateway.core.deps as _deps_mod

    counts: dict[str, int] = {}

    async def _fake(key: str, bucket_limit: int, window: int) -> tuple[bool, int]:
        prefix, sep, _ = key.partition(":")
        if not sep:
            return False, 0
        counts[prefix] = counts.get(prefix, 0) + 1
        if counts[prefix] > limit:
            retry_after = window - (int(time.time()) % window)
            return True, max(retry_after, 1)
        return False, 0

    monkeypatch.setattr(_deps_mod, "is_rate_limited", _fake)


@pytest.mark.asyncio
async def test_upload_rate_limit_enforced(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_limiter(monkeypatch, limit=2)

    email = f"rl_up_{uuid.uuid4().hex[:8]}@example.com"
    token = (await _register(client, email))["token"]

    for i in range(2):
        resp = await _upload(client, token, f"rl_{i}.png", _png_bytes())
        assert resp.status_code == 202, resp.text

    resp = await _upload(client, token, "rl_3.png", _png_bytes())
    assert resp.status_code == 429
    assert resp.json()["code"] == "RATE_LIMITED"
    assert resp.headers["Retry-After"]


@pytest.mark.asyncio
async def test_download_rate_limit_enforced(
    client: AsyncClient, commands_reader: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_limiter(monkeypatch, limit=2)

    scan_id, _, token = await _completed_scan(client, commands_reader)
    headers = {"Authorization": f"Bearer {token}"}
    url = f"/api/v1/scans/{scan_id}/outputs/ENHANCED/url"

    for _ in range(2):
        resp = await client.get(url, headers=headers)
        assert resp.status_code == 200, resp.text

    resp = await client.get(url, headers=headers)
    assert resp.status_code == 429
    assert resp.json()["code"] == "RATE_LIMITED"
