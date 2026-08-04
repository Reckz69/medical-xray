"""Endpoint-specific rate limiting backed by Redis fixed windows.

Limits are per-endpoint, not global:
  login 5/min/IP · register 3/day/IP · upload 20/h/user · download 300/h/user
"""

import time

from gateway.core.redis import redis


async def is_rate_limited(key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
    """Check/consume a token in a fixed window.

    Returns (limited, retry_after_seconds). Consumes one token per call even
    when already limited (never trust the client to back off).
    """
    window = int(time.time()) // window_seconds
    bucket = f"rl:{key}:{window}"
    count = await redis.incr(bucket)
    if count == 1:
        await redis.expire(bucket, window_seconds + 1)
    if count > limit:
        retry_after = window_seconds - (int(time.time()) % window_seconds)
        return True, max(retry_after, 1)
    return False, 0
