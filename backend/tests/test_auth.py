"""Auth domain integration tests.

Exercises the full register -> login -> refresh -> logout -> me lifecycle
against real Docker infra (Postgres). Rate limiting and Redis blacklist
are monkeypatched in conftest.py.

Error envelope: {code, message, trace_id, status}
Success envelope: {success, data, meta, trace_id}
"""

from __future__ import annotations

import uuid

import httpx
import pytest
from httpx import AsyncClient

# ── Shared test data ────────────────────────────────────────────────────────
_EMAIL = f"test_{uuid.uuid4().hex[:8]}@example.com"
_PASSWORD = "S3cure!Pass"
_NAME = "Test User"


def _extract_refresh_cookie(response: httpx.Response) -> str | None:
    """Pull refresh_token value from Set-Cookie header."""
    for header in response.headers.get_list("set-cookie"):
        if header.startswith("refresh_token="):
            return header.split("=", 1)[1].split(";", 1)[0]
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Register
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_register_success(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"name": _NAME, "email": _EMAIL, "password": _PASSWORD},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["user"]["email"] == _EMAIL
    assert body["data"]["user"]["role"] == "patient"
    assert body["data"]["access_token"]
    assert body["data"]["token_type"] == "bearer"
    assert _extract_refresh_cookie(resp) is not None


@pytest.mark.asyncio
async def test_register_duplicate_email_returns_409(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"name": _NAME, "email": _EMAIL, "password": _PASSWORD},
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["code"] == "CONFLICT"


@pytest.mark.asyncio
async def test_register_validation_error(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"name": "", "email": "bad", "password": "short"},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"


# ═══════════════════════════════════════════════════════════════════════════
# Login
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_login_success(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": _EMAIL, "password": _PASSWORD},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["access_token"]
    assert body["data"]["user"]["email"] == _EMAIL
    assert _extract_refresh_cookie(resp) is not None


@pytest.mark.asyncio
async def test_login_bad_password_returns_401(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": _EMAIL, "password": "wrong-password"},
    )
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_login_unknown_email_returns_401(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent@example.com", "password": _PASSWORD},
    )
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "UNAUTHORIZED"


# ═══════════════════════════════════════════════════════════════════════════
# Me
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_me_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_me_returns_current_user(client: AsyncClient) -> None:
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": _EMAIL, "password": _PASSWORD},
    )
    token = login_resp.json()["data"]["access_token"]

    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["email"] == _EMAIL


@pytest.mark.asyncio
async def test_me_with_invalid_token_returns_401(client: AsyncClient) -> None:
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid.token.here"},
    )
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "UNAUTHORIZED"


# ═══════════════════════════════════════════════════════════════════════════
# Refresh
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_refresh_rotates_token(client: AsyncClient) -> None:
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": _EMAIL, "password": _PASSWORD},
    )
    old_access = login_resp.json()["data"]["access_token"]
    cookie = _extract_refresh_cookie(login_resp)
    assert cookie is not None

    refresh_resp = await client.post(
        "/api/v1/auth/refresh",
        headers={"Cookie": f"refresh_token={cookie}"},
    )
    assert refresh_resp.status_code == 200
    body = refresh_resp.json()
    assert body["success"] is True
    new_access = body["data"]["access_token"]
    assert new_access
    assert new_access != old_access

    new_cookie = _extract_refresh_cookie(refresh_resp)
    assert new_cookie is not None
    assert new_cookie != cookie


@pytest.mark.asyncio
async def test_refresh_without_cookie_returns_token_expired(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/auth/refresh")
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "TOKEN_EXPIRED"


@pytest.mark.asyncio
async def test_refresh_with_invalid_cookie_returns_token_expired(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/refresh",
        headers={"Cookie": "refresh_token=garbage.token.value"},
    )
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "TOKEN_EXPIRED"


@pytest.mark.asyncio
async def test_refresh_reused_old_token_returns_token_expired(client: AsyncClient) -> None:
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": _EMAIL, "password": _PASSWORD},
    )
    old_cookie = _extract_refresh_cookie(login_resp)
    assert old_cookie is not None

    # First refresh — should succeed and rotate
    await client.post(
        "/api/v1/auth/refresh",
        headers={"Cookie": f"refresh_token={old_cookie}"},
    )

    # Second refresh with same old cookie — version mismatch
    resp = await client.post(
        "/api/v1/auth/refresh",
        headers={"Cookie": f"refresh_token={old_cookie}"},
    )
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "TOKEN_EXPIRED"


# ═══════════════════════════════════════════════════════════════════════════
# Logout
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_logout_returns_204(client: AsyncClient) -> None:
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": _EMAIL, "password": _PASSWORD},
    )
    cookie = _extract_refresh_cookie(login_resp)
    assert cookie is not None

    resp = await client.post(
        "/api/v1/auth/logout",
        headers={"Cookie": f"refresh_token={cookie}"},
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_logout_then_refresh_fails(client: AsyncClient) -> None:
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": _EMAIL, "password": _PASSWORD},
    )
    cookie = _extract_refresh_cookie(login_resp)
    assert cookie is not None

    # Logout bumps version
    await client.post(
        "/api/v1/auth/logout",
        headers={"Cookie": f"refresh_token={cookie}"},
    )

    # Refresh with old cookie — version mismatch (blacklist is patched away,
    # but the version bump still causes rejection)
    resp = await client.post(
        "/api/v1/auth/refresh",
        headers={"Cookie": f"refresh_token={cookie}"},
    )
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "TOKEN_EXPIRED"


# ═══════════════════════════════════════════════════════════════════════════
# Forgot password (placeholder)
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_forgot_password_returns_202(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": _EMAIL},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["success"] is True


# ═══════════════════════════════════════════════════════════════════════════
# Envelope & health
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_error_envelope_has_trace_id(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": _EMAIL, "password": "wrong"},
    )
    body = resp.json()
    assert "trace_id" in body
    assert isinstance(body["trace_id"], str)
    assert len(body["trace_id"]) > 0


@pytest.mark.asyncio
async def test_health_live(client: AsyncClient) -> None:
    resp = await client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
