"""Shared fixtures for integration tests.

Uses httpx.AsyncClient with ASGITransport to hit the FastAPI app directly.
Creates fresh DB engine per test. Patches rate-limiting and Redis blacklist
to avoid event-loop binding issues with module-level singletons.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from gateway.core.config import settings
from gateway.core.db import get_db
from gateway.main import app


# ── Bypass Redis entirely in tests ──────────────────────────────────────────
@pytest.fixture(autouse=True)
def _bypass_redis(monkeypatch):
    """Patch rate-limiting and JTI blacklist to skip Redis.

    IMPORTANT: `deps.py` imports `is_rate_limited` via ``from ... import``,
    so the closure in the rate-limit dependency references the name
    ``gateway.core.deps.is_rate_limited`` — we must patch *that* reference,
    not the one in ``gateway.core.rate_limit``.
    """
    import gateway.core.deps as _deps_mod
    import gateway.domains.auth.service as _auth_svc

    async def _no_rate_limit(_key: str, _limit: int, _window: int) -> tuple[bool, int]:
        return False, 0

    async def _not_blacklisted(_jti: str) -> bool:
        return False

    async def _noop_blacklist(_jti: str, _expires_at) -> None:
        return None

    monkeypatch.setattr(_deps_mod, "is_rate_limited", _no_rate_limit)
    monkeypatch.setattr(_auth_svc, "_is_blacklisted", _not_blacklisted)
    monkeypatch.setattr(_auth_svc, "_blacklist_jti", _noop_blacklist)


# ── Fresh DB session per test ───────────────────────────────────────────────
@pytest_asyncio.fixture
async def _fresh_engine():
    engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=5,
    )
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def client(_fresh_engine) -> AsyncIterator[AsyncClient]:
    session_factory = async_sessionmaker(
        _fresh_engine, class_=AsyncSession, expire_on_commit=False,
    )

    async def _override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c

    app.dependency_overrides.pop(get_db, None)
