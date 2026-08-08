"""Worker registry — shared heartbeat schema + Redis read/write helpers.

The worker writes heartbeats; the gateway reads and aggregates them for
``/health/infra``. The payload schema and Redis key layout live here so both
sides agree without importing each other's application packages.

Crash handling is eventual consistency: a worker that stops beating has its
``worker:heartbeat:<id>`` key expire after the TTL, and the gateway prunes the
stale entry from ``worker:active`` when it observes the expired key. Nothing in
this registry is authoritative — it is operational telemetry only.
"""

from __future__ import annotations

import json
import logging
import socket
from datetime import UTC, datetime
from typing import Any

from gateway.core.config import settings
from gateway.core.redis import redis

logger = logging.getLogger("denoise")

HEARTBEAT_SCHEMA_VERSION = 1
ACTIVE_SET_KEY = "worker:active"
HEARTBEAT_KEY_PREFIX = "worker:heartbeat"
DEFAULT_CAPABILITIES = ["denoise"]


def worker_id() -> str:
    """Stable identifier for this worker process (hostname or env override)."""
    return socket.gethostname() or "worker"


def heartbeat_key(worker: str) -> str:
    return f"{HEARTBEAT_KEY_PREFIX}:{worker}"


def build_heartbeat(
    *,
    worker: str,
    uptime_seconds: float,
    model_name: str,
    model_version: str,
    gpu_name: str | None = None,
    capabilities: list[str] | None = None,
) -> dict[str, Any]:
    """A versioned heartbeat payload describing a live worker."""
    return {
        "schema_version": HEARTBEAT_SCHEMA_VERSION,
        "worker_id": worker,
        "heartbeat_at": datetime.now(UTC).isoformat(),
        "uptime_seconds": round(uptime_seconds, 1),
        "model_name": model_name,
        "model_version": model_version,
        "gpu": gpu_name,
        "capabilities": capabilities or list(DEFAULT_CAPABILITIES),
    }


# ── Writer side (worker) ────────────────────────────────────────────────────
async def register() -> None:
    """Add this worker to the active registry (idempotent)."""
    try:
        await redis.sadd(ACTIVE_SET_KEY, worker_id())
    except Exception as exc:  # noqa: BLE001 — telemetry must never crash the worker
        logger.warning("could not register worker in redis: %s", exc)


async def unregister() -> None:
    """Remove this worker from the registry and drop its heartbeat key."""
    try:
        await redis.srem(ACTIVE_SET_KEY, worker_id())
        await redis.delete(heartbeat_key(worker_id()))
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not unregister worker from redis: %s", exc)


async def write_heartbeat(model: Any, uptime_seconds: float) -> None:
    """Write this worker's heartbeat and re-affirm registry membership."""
    try:
        payload = build_heartbeat(
            worker=worker_id(),
            uptime_seconds=uptime_seconds,
            model_name=model.model_name,
            model_version=model.model_version,
            gpu_name=getattr(model, "gpu_name", None),
        )
        await redis.set(
            heartbeat_key(worker_id()),
            json.dumps(payload, separators=(",", ":")),
            ex=settings.worker_heartbeat_ttl_seconds,
        )
        await redis.sadd(ACTIVE_SET_KEY, worker_id())
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not write worker heartbeat: %s", exc)


# ── Reader side (gateway) ───────────────────────────────────────────────────
async def read_worker_states() -> list[dict[str, Any]]:
    """SMEMBERS the registry, fetches each heartbeat, prunes stale entries.

    Returns the parsed, live heartbeat payloads (stale/corrupt entries are
    removed from the registry and omitted from the result). Never raises — on
    a Redis outage it degrades to an empty list.
    """
    try:
        members = await redis.smembers(ACTIVE_SET_KEY)
    except Exception as exc:  # noqa: BLE001 — diagnostics must never fail the endpoint
        logger.warning("could not read worker registry: %s", exc)
        return []

    states: list[dict[str, Any]] = []
    for member in members:
        try:
            raw = await redis.get(heartbeat_key(member))
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not read heartbeat for %s: %s", member, exc)
            continue
        if not raw:
            await _prune(member)
            continue
        try:
            states.append(json.loads(raw))
        except ValueError as exc:
            logger.warning("ignoring corrupt heartbeat for %s: %s", member, exc)
            await _prune(member)
    return states


async def _prune(worker: str) -> None:
    try:
        await redis.srem(ACTIVE_SET_KEY, worker)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not prune stale worker %s: %s", worker, exc)
