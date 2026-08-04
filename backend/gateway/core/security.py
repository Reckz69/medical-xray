"""JWT + password-hashing primitives.

Passwords are hashed with bcrypt (never passlib — unmaintained).
Access tokens carry role + org claims; refresh tokens embed a `ver` claim
(the user's ``refresh_token_version``) so logout/rotation invalidates the
whole token family instantly via a version mismatch at decode time.
"""

import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from gateway.core.config import settings

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def _base_claims(token_type: str, subject: str) -> dict:
    now = datetime.now(UTC)
    if token_type == ACCESS_TOKEN_TYPE:
        expires = now + timedelta(minutes=settings.access_token_expire_minutes)
    else:
        expires = now + timedelta(days=settings.refresh_token_expire_days)
    return {
        "iss": settings.jwt_issuer,
        "sub": subject,
        "iat": now,
        "exp": expires,
        "type": token_type,
        "jti": uuid.uuid4().hex,
    }


def create_access_token(
    user_id: str,
    role: str,
    organization_id: str,
) -> str:
    claims = _base_claims(ACCESS_TOKEN_TYPE, str(user_id))
    claims["role"] = role
    claims["org"] = str(organization_id)
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str, version: int = 0) -> str:
    claims = _base_claims(REFRESH_TOKEN_TYPE, str(user_id))
    claims["ver"] = version
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    """Decode + verify signature/expiry. Raises jwt.PyJWTError on failure."""
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        issuer=settings.jwt_issuer,
    )
