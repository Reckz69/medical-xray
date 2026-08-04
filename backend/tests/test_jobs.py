"""Jobs status endpoint tests.

Covers GET /api/v1/jobs/{job_id}: the frontend's polling source for
upload -> queued -> running -> completed. Ownership is enforced through the
owning scan; foreign/missing jobs return 404 (no existence probing).
"""

from __future__ import annotations

import io
import uuid

import numpy as np
import pytest
from httpx import AsyncClient
from PIL import Image

_PASSWORD = "S3cure!Pass"
_NAME = "Jobs User"


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


@pytest.mark.asyncio
async def test_get_job_returns_status_and_scan_status(client: AsyncClient) -> None:
    email = f"job_ok_{uuid.uuid4().hex[:8]}@example.com"
    token = (await _register(client, email))["token"]

    upload = await _upload(client, token, "chest.png", _png_bytes())
    assert upload.status_code == 202, upload.text
    data = upload.json()["data"]
    job_id = data["job_id"]
    assert data["job_status"] == "QUEUED"

    resp = await client.get(
        f"/api/v1/jobs/{job_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["id"] == job_id
    assert body["scan_id"] == data["scan"]["id"]
    assert body["status"] == "QUEUED"
    assert body["scan_status"] == "QUEUED"
    assert body["attempt"] == 0
    assert body["max_attempts"] == 3
    assert body["error"] is None
    assert body["created_at"]
    assert body["started_at"] is None
    assert body["finished_at"] is None


@pytest.mark.asyncio
async def test_get_job_requires_auth(client: AsyncClient) -> None:
    resp = await client.get(f"/api/v1/jobs/{uuid.uuid4()}")
    assert resp.status_code == 401
    assert resp.json()["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_get_foreign_job_returns_404(client: AsyncClient) -> None:
    email_a = f"job_a_{uuid.uuid4().hex[:8]}@example.com"
    email_b = f"job_b_{uuid.uuid4().hex[:8]}@example.com"
    token_a = (await _register(client, email_a))["token"]
    token_b = (await _register(client, email_b))["token"]

    upload = await _upload(client, token_a, "chest.png", _png_bytes())
    job_id = upload.json()["data"]["job_id"]

    resp = await client.get(
        f"/api/v1/jobs/{job_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_get_nonexistent_job_returns_404(client: AsyncClient) -> None:
    email = f"job_nf_{uuid.uuid4().hex[:8]}@example.com"
    token = (await _register(client, email))["token"]

    resp = await client.get(
        f"/api/v1/jobs/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"
