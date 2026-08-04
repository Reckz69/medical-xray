"""Domain error codes and the exception hierarchy.

Every endpoint error returns `{ code, message, trace_id, status }` where
`code` is a stable machine-readable string the frontend switches on. HTTP
status is carried for convenience only.
"""

from __future__ import annotations

from starlette.responses import JSONResponse

# ── Stable error codes (OpenAPI `ErrorCode` enum) ─────────────────────────────
UNAUTHORIZED = "UNAUTHORIZED"
TOKEN_EXPIRED = "TOKEN_EXPIRED"
FORBIDDEN = "FORBIDDEN"
NOT_FOUND = "NOT_FOUND"
CONFLICT = "CONFLICT"
VALIDATION_ERROR = "VALIDATION_ERROR"
UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
SCAN_TOO_LARGE = "SCAN_TOO_LARGE"
RATE_LIMITED = "RATE_LIMITED"
INTERNAL_ERROR = "INTERNAL_ERROR"


class ApiError(Exception):
    """Base class for all controllable API errors."""

    code: str = INTERNAL_ERROR
    status: int = 500

    def __init__(self, message: str, code: str | None = None, status: int | None = None):
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status is not None:
            self.status = status


class UnauthorizedError(ApiError):
    code = UNAUTHORIZED
    status = 401


class TokenExpiredError(ApiError):
    code = TOKEN_EXPIRED
    status = 401


class ForbiddenError(ApiError):
    code = FORBIDDEN
    status = 403


class NotFoundError(ApiError):
    code = NOT_FOUND
    status = 404


class ConflictError(ApiError):
    code = CONFLICT
    status = 409


class ValidationError_(ApiError):
    code = VALIDATION_ERROR
    status = 422


class UnsupportedFormatError(ApiError):
    code = UNSUPPORTED_FORMAT
    status = 415


class ScanTooLargeError(ApiError):
    code = SCAN_TOO_LARGE
    status = 413


class RateLimitedError(ApiError):
    code = RATE_LIMITED
    status = 429

    def __init__(self, message: str, retry_after: int = 60):
        super().__init__(message)
        self.retry_after = retry_after


def error_body(code: str, message: str, trace_id: str, status: int) -> dict:
    return {"code": code, "message": message, "trace_id": trace_id, "status": status}


def api_error_response(exc: ApiError, trace_id: str) -> JSONResponse:
    headers = {}
    if isinstance(exc, RateLimitedError):
        headers["Retry-After"] = str(exc.retry_after)
    return JSONResponse(
        status_code=exc.status,
        content=error_body(exc.code, exc.message, trace_id, exc.status),
        headers=headers,
    )
