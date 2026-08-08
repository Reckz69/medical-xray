"""/health/infra tests (Sprint 4F operational health).

Covers the heartbeat payload schema, the endpoint contract (checks, checked_at,
app_version/git_sha, worker aggregation, queue depth that degrades to null),
the configurable auth gate, and registry pruning of stale workers.
"""

from __future__ import annotations

import json
import uuid

import pytest
from httpx import AsyncClient

from gateway.core.config import settings
from gateway.core.redis import redis
from gateway.core.worker_registry import (
    ACTIVE_SET_KEY,
    build_heartbeat,
    heartbeat_key,
    read_worker_states,
)

_PASSWORD = "S3cure!Pass"
_NAME = "Health User"


@pytest.mark.asyncio
async def test_build_heartbeat_payload() -> None:
    payload = build_heartbeat(
        worker="worker-1",
        uptime_seconds=3820.4,
        model_name="n2n_unet",
        model_version="weights-v1",
        gpu_name="cpu",
    )
    assert payload["schema_version"] == 1
    assert payload["worker_id"] == "worker-1"
    assert payload["uptime_seconds"] == 3820.4
    assert payload["model_name"] == "n2n_unet"
    assert payload["model_version"] == "weights-v1"
    assert payload["gpu"] == "cpu"
    assert payload["capabilities"] == ["denoise"]
    assert payload["heartbeat_at"]


@pytest.mark.asyncio
async def test_worker_registry_prunes_stale_members() -> None:
    live = f"live-{uuid.uuid4().hex[:8]}"
    stale = f"stale-{uuid.uuid4().hex[:8]}"
    await redis.sadd(ACTIVE_SET_KEY, live, stale)
    await redis.set(
        heartbeat_key(live),
        json.dumps(
            build_heartbeat(
                worker=live,
                uptime_seconds=5.0,
                model_name="n2n_unet",
                model_version="weights-v1",
            )
        ),
        ex=30,
    )
    # `stale` is registered but has no heartbeat key -> simulates a crash whose
    # key expired; the reader must prune it.

    states = await read_worker_states()

    remaining = await redis.smembers(ACTIVE_SET_KEY)
    assert live in remaining
    assert stale not in remaining
    assert any(s.get("worker_id") == live for s in states)

    await redis.srem(ACTIVE_SET_KEY, live)
    await redis.delete(heartbeat_key(live))


@pytest.mark.asyncio
async def test_health_infra_contract(
    client: AsyncClient,
    monkeypatch,
) -> None:
    payload = build_heartbeat(
        worker="worker-1",
        uptime_seconds=99.0,
        model_name="n2n_unet",
        model_version="weights-v1",
        gpu_name="cpu",
    )

    async def _checks() -> dict:
        return {"postgres": "ok", "redis": "ok", "rabbitmq": "ok", "storage": "ok"}

    async def _states() -> list:
        return [payload]

    async def _depth() -> int:
        return 2

    monkeypatch.setattr("gateway.main._run_ready_checks", _checks)
    monkeypatch.setattr("gateway.main.read_worker_states", _states)
    monkeypatch.setattr("gateway.main._queue_depth", _depth)

    resp = await client.get("/health/infra")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["status"] == "ok"
    assert body["checked_at"]
    assert body["app_version"] == settings.app_version
    assert body["git_sha"] is None or isinstance(body["git_sha"], str)
    assert body["model_version"] == "weights-v1"
    assert body["checks"] == {
        "postgres": "ok",
        "redis": "ok",
        "rabbitmq": "ok",
        "storage": "ok",
    }
    assert body["worker"]["alive"] is True
    assert body["worker"]["model_loaded"] is True
    assert body["worker"]["model_version"] == "weights-v1"
    assert body["worker"]["last_heartbeat"] == payload["heartbeat_at"]
    assert body["rabbitmq"] == {"queue_name": "inference.worker", "queue_depth": 2}


@pytest.mark.asyncio
async def test_health_infra_degraded_when_worker_dead(
    client: AsyncClient,
    monkeypatch,
) -> None:
    async def _checks() -> dict:
        return {"postgres": "ok", "redis": "ok", "rabbitmq": "ok", "storage": "ok"}

    async def _states() -> list:
        return []

    monkeypatch.setattr("gateway.main._run_ready_checks", _checks)
    monkeypatch.setattr("gateway.main.read_worker_states", _states)

    resp = await client.get("/health/infra")
    assert resp.status_code == 503, resp.text
    body = resp.json()

    assert body["status"] == "degraded"
    assert body["worker"]["alive"] is False
    assert body["worker"]["model_loaded"] is False
    assert body["model_version"] == settings.model_version


@pytest.mark.asyncio
async def test_health_infra_queue_depth_degrades_to_null(
    client: AsyncClient,
    monkeypatch,
) -> None:
    async def _checks() -> dict:
        return {"postgres": "ok", "redis": "ok", "rabbitmq": "ok", "storage": "ok"}

    async def _states() -> list:
        return [
            build_heartbeat(
                worker="worker-1",
                uptime_seconds=1.0,
                model_name="n2n_unet",
                model_version="weights-v1",
            )
        ]

    async def _depth() -> None:
        return None

    monkeypatch.setattr("gateway.main._run_ready_checks", _checks)
    monkeypatch.setattr("gateway.main.read_worker_states", _states)
    monkeypatch.setattr("gateway.main._queue_depth", _depth)

    resp = await client.get("/health/infra")
    assert resp.status_code == 200, resp.text
    assert resp.json()["rabbitmq"]["queue_depth"] is None


async def _register(client: AsyncClient, email: str) -> str:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"name": _NAME, "email": email, "password": _PASSWORD},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_health_infra_auth_required_when_enabled(
    client: AsyncClient,
    monkeypatch,
) -> None:
    async def _checks() -> dict:
        return {"postgres": "ok", "redis": "ok", "rabbitmq": "ok", "storage": "ok"}

    async def _states() -> list:
        return [
            build_heartbeat(
                worker="worker-1",
                uptime_seconds=1.0,
                model_name="n2n_unet",
                model_version="weights-v1",
            )
        ]

    monkeypatch.setattr("gateway.main._run_ready_checks", _checks)
    monkeypatch.setattr("gateway.main.read_worker_states", _states)
    monkeypatch.setattr(settings, "health_infra_auth", True)

    unauth = await client.get("/health/infra")
    assert unauth.status_code == 401, unauth.text

    token = await _register(client, f"hlt_{uuid.uuid4().hex[:8]}@example.com")
    authed = await client.get(
        "/health/infra", headers={"Authorization": f"Bearer {token}"}
    )
    assert authed.status_code == 200, authed.text
