"""Async Redis client.

Redis is a cache / rate-limiter / session-blacklist ONLY — never authoritative.
If Redis crashes nothing breaks; PostgreSQL is the source of truth.
"""

from redis.asyncio import Redis

from gateway.core.config import settings

redis = Redis.from_url(settings.redis_url, decode_responses=True)
