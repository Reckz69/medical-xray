"""FastAPI application entrypoint.

Assembled from the pieces in `gateway.core`: trace-id middleware, CORS,
envelope + error-code plumbing, and infra health endpoints. Domain routers
(/api/v1/*) are mounted by each domain's `router.py` and included here.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

import aio_pika
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from gateway.core import errors
from gateway.core.config import settings
from gateway.core.db import engine
from gateway.core.logging import configure_logging
from gateway.core.otel import TraceIDMiddleware, get_trace_id
from gateway.core.queue import queue
from gateway.core.redis import redis
from gateway.core.storage import storage
from gateway.domains.auth import auth_router
from gateway.domains.scans import scan_router

logger = logging.getLogger("denoise")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging("DEBUG" if settings.debug else "INFO")
    logger.info("%s starting (env=%s)", settings.app_name, settings.environment)
    try:
        await storage.ensure_bucket()
        logger.info("object storage bucket %r ready", storage.bucket)
    except Exception as exc:  # noqa: BLE001 — startup must not hard-fail on storage
        logger.warning("object storage not reachable at startup: %s", exc)
    yield
    await queue.close()
    await redis.aclose()
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    openapi_url=f"{settings.api_prefix}/openapi.json",
    docs_url="/docs",
    lifespan=lifespan,
)

app.add_middleware(TraceIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(scan_router, prefix=settings.api_prefix)


# ── Error handlers ──────────────────────────────────────────────────────────
@app.exception_handler(errors.ApiError)
async def api_error_handler(request: Request, exc: errors.ApiError) -> JSONResponse:
    return errors.api_error_response(exc, get_trace_id(request))


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    if exc.status_code in (401, 403):
        code = errors.UNAUTHORIZED if exc.status_code == 401 else errors.FORBIDDEN
    else:
        code = errors.NOT_FOUND if exc.status_code == 404 else errors.INTERNAL_ERROR
    detail = errors.error_body(code, str(exc.detail), get_trace_id(request), exc.status_code)
    return JSONResponse(status_code=exc.status_code, content=detail)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    message = exc.errors()[0]["msg"] if exc.errors() else "Validation error"
    detail = errors.error_body(
        errors.VALIDATION_ERROR, message, get_trace_id(request), 422
    )
    return JSONResponse(status_code=422, content=detail)


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled error on %s %s", request.method, request.url.path)
    message = "Internal server error"
    if settings.debug:
        message = f"{type(exc).__name__}: {exc}"
    detail = errors.error_body(
        errors.INTERNAL_ERROR, message, get_trace_id(request), 500
    )
    return JSONResponse(status_code=500, content=detail)


# ── Health ──────────────────────────────────────────────────────────────────
@app.get("/health/live", tags=["health"], include_in_schema=False)
async def health_live() -> dict:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"], include_in_schema=False)
async def health_ready() -> JSONResponse:
    checks: dict[str, str] = {}

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["postgres"] = f"error: {exc}"

    try:
        await redis.ping()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"error: {exc}"

    try:
        connection = await asyncio.wait_for(
            aio_pika.connect(settings.rabbitmq_url), timeout=2
        )
        await connection.close()
        checks["rabbitmq"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["rabbitmq"] = f"error: {exc}"

    try:
        await storage.ensure_bucket()
        checks["storage"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["storage"] = f"error: {exc}"

    ready = all(value == "ok" for value in checks.values())
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ok" if ready else "degraded", "checks": checks},
    )
