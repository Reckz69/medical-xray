"""Scans domain integration tests.

Covers upload validation (extension -> magic bytes -> mime -> decode ->
dimensions -> size -> sha256), object storage persistence, list pagination,
ownership authorization (403 for foreign scans), and soft-delete semantics
for /api/v1/scans.
"""

from __future__ import annotations

import io
import uuid

import httpx
import numpy as np
import pydicom
import pytest
from httpx import AsyncClient
from PIL import Image
from pydicom.uid import ExplicitVRLittleEndian

from gateway.core.config import settings

_PASSWORD = "S3cure!Pass"
_NAME = "Scan User"


# ── Registration / auth helpers ────────────────────────────────────────────
async def _register(client: AsyncClient, email: str) -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"name": _NAME, "email": email, "password": _PASSWORD},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    return {"token": data["access_token"], "user": data["user"]}


# ── Sample image builders ──────────────────────────────────────────────────
def _png_bytes(size: tuple[int, int] = (256, 256)) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(
        np.random.randint(0, 256, (size[1], size[0]), dtype=np.uint8),
        mode="L",
    ).save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_bytes(size: tuple[int, int] = (256, 256)) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(
        np.random.randint(0, 256, (size[1], size[0], 3), dtype=np.uint8),
        mode="RGB",
    ).save(buf, format="JPEG")
    return buf.getvalue()


def _dicom_bytes(rows: int = 128, cols: int = 128) -> bytes:
    ds = pydicom.dataset.Dataset()
    ds.file_meta = pydicom.dataset.FileMetaDataset()
    ds.file_meta.MediaStorageSOPClassUID = pydicom.uid.CTImageStorage
    ds.file_meta.MediaStorageSOPInstanceUID = pydicom.uid.generate_uid()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.SOPClassUID = pydicom.uid.CTImageStorage
    ds.SOPInstanceUID = pydicom.uid.generate_uid()
    ds.PatientName = "Test^Patient"
    ds.Modality = "CT"
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.Rows = rows
    ds.Columns = cols
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.PixelData = np.zeros((rows, cols), dtype=np.uint16).tobytes()

    buf = io.BytesIO()
    ds.save_as(buf, enforce_file_format=True, little_endian=True, implicit_vr=False)
    return buf.getvalue()


async def _upload(
    client: AsyncClient,
    token: str,
    filename: str,
    content: bytes,
    content_type: str = "application/octet-stream",
) -> httpx.Response:
    return await client.post(
        "/api/v1/scans",
        files={"file": (filename, content, content_type)},
        headers={"Authorization": f"Bearer {token}"},
    )


# ═══════════════════════════════════════════════════════════════════════════
# Valid uploads
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_upload_png_success(client: AsyncClient) -> None:
    email = f"scan_png_{uuid.uuid4().hex[:8]}@example.com"
    token = (await _register(client, email))["token"]
    content = _png_bytes()

    resp = await _upload(client, token, "chest.png", content)
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["trace_id"]

    data = body["data"]
    assert data["scan"]["format"] == "PNG"
    assert data["scan"]["status"] == "QUEUED"
    assert data["scan"]["original_name"] == "chest.png"
    assert data["scan"]["width"] == 256
    assert data["scan"]["height"] == 256
    assert data["scan"]["size_bytes"] == len(content)
    assert len(data["scan"]["content_hash"]) == 64
    assert data["job_id"]
    assert data["job_status"] == "QUEUED"


@pytest.mark.asyncio
async def test_upload_jpeg_success(client: AsyncClient) -> None:
    email = f"scan_jpeg_{uuid.uuid4().hex[:8]}@example.com"
    token = (await _register(client, email))["token"]

    resp = await _upload(client, token, "knee.jpg", _jpeg_bytes())
    assert resp.status_code == 202, resp.text
    data = resp.json()["data"]
    assert data["scan"]["format"] == "JPEG"
    assert data["scan"]["status"] == "QUEUED"
    assert data["job_status"] == "QUEUED"


@pytest.mark.asyncio
async def test_upload_dicom_success(client: AsyncClient) -> None:
    email = f"scan_dcm_{uuid.uuid4().hex[:8]}@example.com"
    token = (await _register(client, email))["token"]

    resp = await _upload(client, token, "scan.dcm", _dicom_bytes())
    assert resp.status_code == 202, resp.text
    data = resp.json()["data"]
    assert data["scan"]["format"] == "DICOM"
    assert data["scan"]["width"] == 128
    assert data["scan"]["height"] == 128
    assert data["job_status"] == "QUEUED"


# ═══════════════════════════════════════════════════════════════════════════
# Upload validation failures
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_upload_unsupported_extension(client: AsyncClient) -> None:
    email = f"scan_bad_{uuid.uuid4().hex[:8]}@example.com"
    token = (await _register(client, email))["token"]

    resp = await _upload(client, token, "notes.txt", b"hello world")
    assert resp.status_code == 415
    assert resp.json()["code"] == "UNSUPPORTED_FORMAT"


@pytest.mark.asyncio
async def test_upload_magic_bytes_mismatch(client: AsyncClient) -> None:
    email = f"scan_mismatch_{uuid.uuid4().hex[:8]}@example.com"
    token = (await _register(client, email))["token"]

    # JPEG bytes but a .png filename — magic bytes must win, not the extension
    resp = await _upload(client, token, "fake.png", _jpeg_bytes())
    assert resp.status_code == 415
    assert resp.json()["code"] == "UNSUPPORTED_FORMAT"


@pytest.mark.asyncio
async def test_upload_invalid_image(client: AsyncClient) -> None:
    email = f"scan_invalid_{uuid.uuid4().hex[:8]}@example.com"
    token = (await _register(client, email))["token"]

    # Valid PNG signature but truncated body: magic passes, decode fails
    corrupted = _png_bytes()[:40]
    resp = await _upload(client, token, "corrupt.png", corrupted)
    assert resp.status_code == 422
    assert resp.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_upload_oversized(client: AsyncClient, monkeypatch) -> None:
    email = f"scan_big_{uuid.uuid4().hex[:8]}@example.com"
    token = (await _register(client, email))["token"]

    monkeypatch.setattr(settings, "max_upload_size_mb", 0)

    resp = await _upload(client, token, "big.png", _png_bytes())
    assert resp.status_code == 413
    assert resp.json()["code"] == "SCAN_TOO_LARGE"


@pytest.mark.asyncio
async def test_upload_dimensions_too_small(client: AsyncClient) -> None:
    email = f"scan_small_{uuid.uuid4().hex[:8]}@example.com"
    token = (await _register(client, email))["token"]

    resp = await _upload(client, token, "tiny.png", _png_bytes((32, 32)))
    assert resp.status_code == 422
    assert resp.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_upload_unauthenticated(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/scans",
        files={"file": ("chest.png", _png_bytes(), "image/png")},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "UNAUTHORIZED"


# ═══════════════════════════════════════════════════════════════════════════
# List
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_list_scans_empty(client: AsyncClient) -> None:
    email = f"scan_empty_{uuid.uuid4().hex[:8]}@example.com"
    token = (await _register(client, email))["token"]

    resp = await client.get(
        "/api/v1/scans",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["items"] == []
    assert body["data"]["total"] == 0


@pytest.mark.asyncio
async def test_list_scans_newest_first(client: AsyncClient) -> None:
    email = f"scan_list_{uuid.uuid4().hex[:8]}@example.com"
    token = (await _register(client, email))["token"]

    ids = []
    for name in ("a.png", "b.png", "c.png"):
        resp = await _upload(client, token, name, _png_bytes())
        assert resp.status_code == 202, resp.text
        ids.append(resp.json()["data"]["scan"]["id"])

    resp = await client.get(
        "/api/v1/scans",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 3
    assert [item["id"] for item in data["items"]] == [ids[2], ids[1], ids[0]]

    created_ats = [item["created_at"] for item in data["items"]]
    assert created_ats == sorted(created_ats, reverse=True)


@pytest.mark.asyncio
async def test_list_scans_pagination(client: AsyncClient) -> None:
    email = f"scan_page_{uuid.uuid4().hex[:8]}@example.com"
    token = (await _register(client, email))["token"]

    for i in range(3):
        resp = await _upload(client, token, f"img{i}.png", _png_bytes())
        assert resp.status_code == 202, resp.text

    headers = {"Authorization": f"Bearer {token}"}

    page1 = await client.get("/api/v1/scans?offset=0&limit=2", headers=headers)
    assert page1.status_code == 200
    p1 = page1.json()["data"]
    assert p1["total"] == 3
    assert p1["offset"] == 0
    assert p1["limit"] == 2
    assert len(p1["items"]) == 2

    page2 = await client.get("/api/v1/scans?offset=2&limit=2", headers=headers)
    assert page2.status_code == 200
    p2 = page2.json()["data"]
    assert p2["total"] == 3
    assert len(p2["items"]) == 1

    seen = {item["id"] for item in p1["items"] + p2["items"]}
    assert len(seen) == 3


@pytest.mark.asyncio
async def test_list_scans_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/scans")
    assert resp.status_code == 401
    assert resp.json()["code"] == "UNAUTHORIZED"


# ═══════════════════════════════════════════════════════════════════════════
# Get
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_get_scan(client: AsyncClient) -> None:
    email = f"scan_get_{uuid.uuid4().hex[:8]}@example.com"
    token = (await _register(client, email))["token"]

    upload = await _upload(client, token, "chest.png", _png_bytes())
    scan_id = upload.json()["data"]["scan"]["id"]

    resp = await client.get(
        f"/api/v1/scans/{scan_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["id"] == scan_id
    assert body["data"]["status"] == "QUEUED"
    assert body["data"]["format"] == "PNG"


@pytest.mark.asyncio
async def test_get_nonexistent_scan(client: AsyncClient) -> None:
    email = f"scan_nf_{uuid.uuid4().hex[:8]}@example.com"
    token = (await _register(client, email))["token"]

    resp = await client.get(
        f"/api/v1/scans/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_get_another_users_scan_forbidden(client: AsyncClient) -> None:
    email_a = f"scan_a_{uuid.uuid4().hex[:8]}@example.com"
    email_b = f"scan_b_{uuid.uuid4().hex[:8]}@example.com"
    token_a = (await _register(client, email_a))["token"]
    token_b = (await _register(client, email_b))["token"]

    upload = await _upload(client, token_a, "chest.png", _png_bytes())
    scan_id = upload.json()["data"]["scan"]["id"]

    resp = await client.get(
        f"/api/v1/scans/{scan_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


# ═══════════════════════════════════════════════════════════════════════════
# Delete (soft delete)
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_delete_soft_deletes_scan(client: AsyncClient) -> None:
    email = f"scan_del_{uuid.uuid4().hex[:8]}@example.com"
    token = (await _register(client, email))["token"]
    headers = {"Authorization": f"Bearer {token}"}

    upload = await _upload(client, token, "chest.png", _png_bytes())
    scan_id = upload.json()["data"]["scan"]["id"]

    resp = await client.delete(f"/api/v1/scans/{scan_id}", headers=headers)
    assert resp.status_code == 204

    # Gone after soft delete
    get_resp = await client.get(f"/api/v1/scans/{scan_id}", headers=headers)
    assert get_resp.status_code == 404

    # Excluded from the list
    list_resp = await client.get("/api/v1/scans", headers=headers)
    assert list_resp.json()["data"]["total"] == 0


@pytest.mark.asyncio
async def test_delete_another_users_scan_forbidden(client: AsyncClient) -> None:
    email_a = f"scan_da_{uuid.uuid4().hex[:8]}@example.com"
    email_b = f"scan_db_{uuid.uuid4().hex[:8]}@example.com"
    token_a = (await _register(client, email_a))["token"]
    token_b = (await _register(client, email_b))["token"]

    upload = await _upload(client, token_a, "chest.png", _png_bytes())
    scan_id = upload.json()["data"]["scan"]["id"]

    resp = await client.delete(
        f"/api/v1/scans/{scan_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"

    # Owner can still see it — nothing was deleted
    get_resp = await client.get(
        f"/api/v1/scans/{scan_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert get_resp.status_code == 200


@pytest.mark.asyncio
async def test_delete_nonexistent_scan(client: AsyncClient) -> None:
    email = f"scan_dnf_{uuid.uuid4().hex[:8]}@example.com"
    token = (await _register(client, email))["token"]

    resp = await client.delete(
        f"/api/v1/scans/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"
