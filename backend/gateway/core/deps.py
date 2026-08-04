"""Shared FastAPI dependencies: auth, rate limiting, audit logging."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

import jwt as pyjwt
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.core.config import settings
from gateway.core.db import get_db
from gateway.core.errors import RateLimitedError, TokenExpiredError, UnauthorizedError
from gateway.core.otel import get_trace_id
from gateway.core.rate_limit import is_rate_limited
from gateway.core.security import ACCESS_TOKEN_TYPE, decode_token
from gateway.models.user import STATUS_ACTIVE
from gateway.repositories.audit_repository import AuditLogRepository
from gateway.repositories.user_repository import UserRepository

DBSession = Annotated[AsyncSession, Depends(get_db)]


@dataclass
class CurrentUser:
    id: UUID
    email: str
    name: str
    role: str
    organization_id: UUID


def _extract_bearer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise UnauthorizedError("Missing or malformed Authorization header")
    return token.strip()


async def get_current_user(request: Request, session: DBSession) -> CurrentUser:
    token = _extract_bearer(request)
    try:
        claims = decode_token(token)
    except pyjwt.ExpiredSignatureError as exc:
        raise TokenExpiredError("Access token has expired") from exc
    except pyjwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid access token") from exc

    if claims.get("type") != ACCESS_TOKEN_TYPE:
        raise UnauthorizedError("Token is not an access token")

    try:
        user_id = UUID(claims["sub"])
    except (KeyError, ValueError, TypeError) as exc:
        raise UnauthorizedError("Token missing subject") from exc

    user = await UserRepository(session).get_active_by_id(user_id)
    if user is None or user.status != STATUS_ACTIVE:
        raise UnauthorizedError("Account not found or inactive")

    return CurrentUser(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        organization_id=user.organization_id,
    )


CurrentUserDeps = Annotated[CurrentUser, Depends(get_current_user)]


def rate_limit(
    key: str | Callable[[Request], str],
    limit: int,
    window_seconds: int,
):
    """Build a dependency enforcing a fixed-window Redis limit.

    `key` is either a static string or a callable deriving a key from the
    request (e.g. client IP). Raises `RateLimitedError` (429) when exceeded.
    """

    async def dependency(request: Request) -> None:
        resolved = key(request) if callable(key) else key
        limited, retry_after = await is_rate_limited(resolved, limit, window_seconds)
        if limited:
            raise RateLimitedError("Rate limit exceeded", retry_after=retry_after)

    return dependency


class AuditLogger:
    """Wraps AuditLogRepository and auto-fills ip / user_agent / trace_id."""

    def __init__(self, request: Request, session: AsyncSession) -> None:
        self._request = request
        self._repo = AuditLogRepository(session)

    @property
    def client_ip(self) -> str | None:
        forwarded = self._request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return self._request.client.host if self._request.client else None

    async def log(
        self,
        action: str,
        *,
        user_id: UUID | None = None,
        organization_id: UUID | None = None,
        resource_type: str | None = None,
        resource_id: UUID | None = None,
    ) -> None:
        await self._repo.create(
            action=action,
            user_id=user_id,
            organization_id=organization_id,
            resource_type=resource_type,
            resource_id=resource_id,
            ip=self.client_ip,
            user_agent=self._request.headers.get("user-agent"),
            trace_id=get_trace_id(self._request) or None,
        )


async def get_audit_logger(
    request: Request,
    session: DBSession,
) -> AuditLogger:
    return AuditLogger(request, session)


AuditLoggerDeps = Annotated[AuditLogger, Depends(get_audit_logger)]


# ── Upload / download rate limits (per authenticated user) ────────────────
async def enforce_upload_rate_limit(current_user: CurrentUserDeps) -> None:
    limited, retry_after = await is_rate_limited(
        f"upload:{current_user.id}",
        settings.rate_limit_upload_per_hour,
        3600,
    )
    if limited:
        raise RateLimitedError("Upload rate limit exceeded", retry_after=retry_after)


async def enforce_download_rate_limit(current_user: CurrentUserDeps) -> None:
    limited, retry_after = await is_rate_limited(
        f"download:{current_user.id}",
        settings.rate_limit_download_per_hour,
        3600,
    )
    if limited:
        raise RateLimitedError("Download rate limit exceeded", retry_after=retry_after)
