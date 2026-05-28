"""
Redis client — singleton used for:
- Rate limit counters (sliding window, atomic Lua scripts)
- Embedding cache (hash → vector bytes, avoid re-embedding identical text)
- Celery broker (separate DBs in same Redis instance)
"""
from typing import Any

import redis.asyncio as aioredis
from redis.asyncio import Redis

from app.config import settings

# ── Singleton ─────────────────────────────────────────────────────────────────
_redis_client: Redis | None = None


async def get_redis() -> Redis:
    """Return the singleton Redis client, creating it if needed."""
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=False,  # Keep bytes for embedding cache
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30,
        )
    return _redis_client


async def close_redis() -> None:
    """Close the Redis connection (called on app shutdown)."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


# ── Rate Limit Lua Script ─────────────────────────────────────────────────────
# Atomic sliding-window increment with TTL.
# Returns [current_count, limit_value, is_over_limit (1/0)]
RATE_LIMIT_SCRIPT = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local increment = tonumber(ARGV[2])
local ttl_seconds = tonumber(ARGV[3])

local current = tonumber(redis.call('GET', key) or 0)
local new_value = current + increment

if new_value > limit then
    -- Over limit: don't increment, return over-limit signal
    return {current, limit, 1}
end

redis.call('INCRBY', key, increment)
redis.call('EXPIRE', key, ttl_seconds)
return {new_value, limit, 0}
"""


async def check_and_increment_rate_limit(
    redis: Redis,
    key: str,
    limit: int,
    increment: int,
    ttl_seconds: int,
) -> tuple[int, int, bool]:
    """
    Atomically check and increment a rate limit counter.

    Returns:
        (current_count, limit, is_over_limit)
    """
    result = await redis.eval(RATE_LIMIT_SCRIPT, 1, key, limit, increment, ttl_seconds)  # type: ignore
    return int(result[0]), int(result[1]), bool(result[2])


# ── Embedding Cache Helpers ───────────────────────────────────────────────────
EMBEDDING_CACHE_TTL = 86400 * 7  # 7 days


async def get_cached_embedding(redis: Redis, text_hash: str) -> list[float] | None:
    """Retrieve a cached embedding vector by text hash."""
    import json
    data = await redis.get(f"embed:{text_hash}")
    if data:
        return json.loads(data)
    return None


async def set_cached_embedding(
    redis: Redis, text_hash: str, embedding: list[float]
) -> None:
    """Cache an embedding vector with a 7-day TTL."""
    import json
    await redis.setex(
        f"embed:{text_hash}",
        EMBEDDING_CACHE_TTL,
        json.dumps(embedding),
    )
