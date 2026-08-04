"""Standard response envelope.

Every `/api/v1/*` endpoint returns:

    { "success": true, "data": ..., "meta": ..., "trace_id": "..." }

Errors use `{ code, message, trace_id, status }` (see core/errors.py).
"""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Envelope(BaseModel, Generic[T]):
    success: bool = True
    data: T | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = None


def envelope(data: T | None = None, meta: dict[str, Any] | None = None, trace_id: str = "") -> dict[str, Any]:
    return Envelope(success=True, data=data, meta=meta or {}, trace_id=trace_id or None).model_dump()
