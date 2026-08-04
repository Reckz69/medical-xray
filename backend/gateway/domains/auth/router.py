"""Auth API router.

Mounts under ``{api_prefix}/auth`` in main.py.
Endpoints: register, login, refresh, logout, me, forgot_password.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.core.config import settings
from gateway.core.db import get_db
from gateway.core.deps import CurrentUserDeps, rate_limit
from gateway.core.envelope import envelope
from gateway.core.otel import get_trace_id
from gateway.domains.auth import service as auth_svc
from gateway.schemas.auth import LoginRequest, RegisterRequest, UserOut

router = APIRouter(prefix="/auth", tags=["Auth"])


# ── Rate-limit dependency factories (keyed by client IP) ──────────────────
def _ip_key(prefix: str):
    def _key(request: Request) -> str:
        ip = request.client.host if request.client else "unknown"
        return f"{prefix}:{ip}"
    return _key


_register_rl = Depends(rate_limit(
    _ip_key("register"),
    settings.rate_limit_register_per_day,
    86_400,  # 1 day
))

_login_rl = Depends(rate_limit(
    _ip_key("login"),
    settings.rate_limit_login_per_minute,
    60,
))


# ── POST /auth/register ─────────────────────────────────────────────────
@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    request: Request,
    response: Response,
    body: RegisterRequest,
    session: AsyncSession = Depends(get_db),  # noqa: B008
    _: None = _register_rl,
) -> dict:
    result = await auth_svc.register(
        session,
        request=request,
        response=response,
        name=body.name,
        email=body.email,
        password=body.password,
        organization_name=body.organization_name,
    )
    user = result.pop("user")
    return envelope(
        data={**result, "user": UserOut.model_validate(user, from_attributes=True)},
        trace_id=get_trace_id(request),
    )


# ── POST /auth/login ────────────────────────────────────────────────────
@router.post("/login")
async def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    session: AsyncSession = Depends(get_db),  # noqa: B008
    _: None = _login_rl,
) -> dict:
    result = await auth_svc.login(
        session,
        request=request,
        response=response,
        email=body.email,
        password=body.password,
    )
    user = result.pop("user")
    return envelope(
        data={**result, "user": UserOut.model_validate(user, from_attributes=True)},
        trace_id=get_trace_id(request),
    )


# ── POST /auth/refresh ──────────────────────────────────────────────────
@router.post("/refresh")
async def refresh(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),  # noqa: B008
) -> dict:
    result = await auth_svc.refresh(
        session,
        request=request,
        response=response,
    )
    user = result.pop("user")
    return envelope(
        data={**result, "user": UserOut.model_validate(user, from_attributes=True)},
        trace_id=get_trace_id(request),
    )


# ── POST /auth/logout ───────────────────────────────────────────────────
@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),  # noqa: B008
) -> None:
    await auth_svc.logout(
        session,
        request=request,
        response=response,
    )


# ── GET /auth/me ────────────────────────────────────────────────────────
@router.get("/me")
async def me(
    request: Request,
    current_user: CurrentUserDeps,
) -> dict:
    return envelope(
        data=UserOut(
            id=current_user.id,
            email=current_user.email,
            name=current_user.name,
            role=current_user.role,
            organization_id=current_user.organization_id,
        ),
        trace_id=get_trace_id(request),
    )


# ── POST /auth/forgot-password (placeholder) ────────────────────────────
@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(request: Request) -> dict:
    return envelope(trace_id=get_trace_id(request))
