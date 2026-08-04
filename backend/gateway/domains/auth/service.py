"""Authentication service — register, login, refresh, logout.

All mutations run in a single async transaction. Refresh-token rotation bumps
``credentials.refresh_token_version`` so every outstanding refresh token in
the family is invalidated instantly. Revoked JTIs are blacklisted in Redis
with a TTL equal to the token's remaining lifetime.

Anti-enumeration: login verifies a dummy bcrypt hash when the email is not
found, making user-enumeration timing attacks impractical.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

import jwt as pyjwt
from sqlalchemy.exc import IntegrityError
from starlette.requests import Request
from starlette.responses import Response

from gateway.core.config import settings
from gateway.core.errors import (
    ConflictError,
    ForbiddenError,
    TokenExpiredError,
    UnauthorizedError,
)
from gateway.core.redis import redis
from gateway.core.security import (
    REFRESH_TOKEN_TYPE,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from gateway.repositories.audit_repository import AuditLogRepository
from gateway.repositories.credential_repository import CredentialRepository
from gateway.repositories.organization_repository import OrganizationRepository
from gateway.repositories.user_repository import UserRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# ── Dummy hash to prevent timing-based user enumeration on login ─────────
_DUMMY_HASH = "$2b$12$Kx/9Gh4QXpVp0eHbHqKqZuYxVZqVZqVZqVZqVZqVZqVZqVZqVZq"

# ── Redis blacklist key: blk:<jti> ──────────────────────────────────────
_BLACKLIST_PREFIX = "blk:"


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


# ── Cookie helpers ───────────────────────────────────────────────────────
def _refresh_token_max_age() -> int:
    """Seconds until the refresh cookie expires (matches JWT exp)."""
    return settings.refresh_token_expire_days * 86_400


def set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=token,
        max_age=_refresh_token_max_age(),
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite=settings.refresh_cookie_samesite,
        path=settings.refresh_cookie_path,
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=settings.refresh_cookie_path,
    )


# ── Blacklist helpers ────────────────────────────────────────────────────
async def _blacklist_jti(jti: str, expires_at: datetime) -> None:
    ttl = max(int((expires_at - datetime.now(UTC)).total_seconds()), 1)
    await redis.set(f"{_BLACKLIST_PREFIX}{jti}", "1", ex=ttl)


async def _is_blacklisted(jti: str) -> bool:
    return await redis.exists(f"{_BLACKLIST_PREFIX}{jti}")


# ── Access + refresh token pair ──────────────────────────────────────────
async def _issue_tokens(
    user_id: str, role: str, org_id: str, version: int
) -> tuple[dict, str]:
    """Return (response_dict, refresh_token_str)."""
    access = create_access_token(user_id, role, org_id)
    refresh = create_refresh_token(user_id, version)
    body = {
        "access_token": access,
        "token_type": "bearer",
        "expires_in": settings.access_token_expire_minutes * 60,
    }
    return body, refresh


# ── Audit shorthand ──────────────────────────────────────────────────────
async def _audit(
    audit: AuditLogRepository,
    *,
    action: str,
    request: Request,
    user_id: UUID | None = None,
    organization_id: UUID | None = None,
) -> None:
    await audit.create(
        action=action,
        user_id=user_id,
        organization_id=organization_id,
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        trace_id=request.state.trace_id or None,
    )


# ══════════════════════════════════════════════════════════════════════════
#  PUBLIC API
# ══════════════════════════════════════════════════════════════════════════
async def register(
    session: AsyncSession,
    *,
    request: Request,
    response: Response,
    name: str,
    email: str,
    password: str,
    organization_name: str | None = None,
) -> dict:
    """Create org + user + credential. Returns token pair dict.

    Raises
    ------
    ForbiddenError  — signup disabled.
    ConflictError   — email already registered.
    """
    if not settings.enable_signup:
        raise ForbiddenError("Signup is disabled")

    org_repo = OrganizationRepository(session)
    user_repo = UserRepository(session)
    cred_repo = CredentialRepository(session)
    audit = AuditLogRepository(session)

    org = await org_repo.create(organization_name or name)

    try:
        user = await user_repo.create(
            organization_id=org.id,
            email=email,
            name=name,
            role="patient",
        )
        await cred_repo.upsert_password(user.id, hash_password(password))
    except IntegrityError:
        await session.rollback()
        raise ConflictError(f"Email {email} is already registered")

    await _audit(audit, action="REGISTER", request=request, user_id=user.id, organization_id=org.id)
    await session.commit()

    body, refresh_token = await _issue_tokens(str(user.id), user.role, str(org.id), 0)
    set_refresh_cookie(response, refresh_token)
    return {**body, "user": user}


async def login(
    session: AsyncSession,
    *,
    request: Request,
    response: Response,
    email: str,
    password: str,
) -> dict:
    """Authenticate, issue tokens, set refresh cookie.

    Raises
    ------
    UnauthorizedError — bad credentials.
    """
    user_repo = UserRepository(session)
    cred_repo = CredentialRepository(session)
    audit = AuditLogRepository(session)

    user = await user_repo.get_by_email(email)

    # Always verify (dummy hash if user not found) to prevent timing leaks
    if user is None:
        verify_password(password, _DUMMY_HASH)
        raise UnauthorizedError("Invalid email or password")

    cred = await cred_repo.get_by_user_id(user.id)
    if cred is None or not verify_password(password, cred.password_hash):
        raise UnauthorizedError("Invalid email or password")

    await user_repo.touch_last_login(user.id)
    await _audit(audit, action="LOGIN", request=request, user_id=user.id, organization_id=user.organization_id)
    await session.commit()

    body, refresh_token = await _issue_tokens(str(user.id), user.role, str(user.organization_id), cred.refresh_token_version)
    set_refresh_cookie(response, refresh_token)
    return {**body, "user": user}


async def refresh(
    session: AsyncSession,
    *,
    request: Request,
    response: Response,
) -> dict:
    """Rotate refresh token. Returns new access token + user.

    Raises
    ------
    TokenExpiredError — token invalid / version mismatch / blacklisted.
    """
    token = request.cookies.get(settings.refresh_cookie_name, "")
    if not token:
        raise TokenExpiredError("No refresh token provided")

    try:
        claims = decode_token(token)
    except pyjwt.ExpiredSignatureError:
        raise TokenExpiredError("Refresh token has expired")
    except pyjwt.PyJWTError:
        raise TokenExpiredError("Invalid refresh token")

    if claims.get("type") != REFRESH_TOKEN_TYPE:
        raise TokenExpiredError("Token is not a refresh token")

    if await _is_blacklisted(claims["jti"]):
        raise TokenExpiredError("Refresh token has been revoked")

    user_repo = UserRepository(session)
    cred_repo = CredentialRepository(session)
    audit = AuditLogRepository(session)

    try:
        user_id = UUID(claims["sub"])
    except (KeyError, ValueError, TypeError):
        raise TokenExpiredError("Refresh token missing subject")

    user = await user_repo.get_active_by_id(user_id)
    if user is None:
        raise TokenExpiredError("Account not found")

    cred = await cred_repo.get_refresh_version(user_id)
    if claims.get("ver") != cred:
        raise TokenExpiredError("Refresh token version mismatch")

    new_version = await cred_repo.bump_refresh_version(user_id)
    await _audit(audit, action="REFRESH", request=request, user_id=user.id, organization_id=user.organization_id)
    await session.commit()

    body, refresh_token = await _issue_tokens(str(user.id), user.role, str(user.organization_id), new_version)
    set_refresh_cookie(response, refresh_token)
    return {**body, "user": user}


async def logout(
    session: AsyncSession,
    *,
    request: Request,
    response: Response,
) -> None:
    """Revoke refresh token family + blacklist jti. Clear cookie."""
    token = request.cookies.get(settings.refresh_cookie_name, "")
    if not token:
        clear_refresh_cookie(response)
        return

    try:
        claims = decode_token(token)
    except (pyjwt.ExpiredSignatureError, pyjwt.PyJWTError):
        clear_refresh_cookie(response)
        return

    if claims.get("type") != REFRESH_TOKEN_TYPE:
        clear_refresh_cookie(response)
        return

    cred_repo = CredentialRepository(session)

    try:
        user_id = UUID(claims["sub"])
    except (KeyError, ValueError, TypeError):
        clear_refresh_cookie(response)
        return

    await cred_repo.bump_refresh_version(user_id)
    await _blacklist_jti(claims["jti"], datetime.fromtimestamp(claims["exp"], tz=UTC))
    await session.commit()
    clear_refresh_cookie(response)
