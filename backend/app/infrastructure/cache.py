"""Generic Redis cache helpers with fail-open behavior.

All functions swallow Redis errors rather than propagating them to callers.
A Redis failure must never break the analysis pipeline — caching is an
optimisation, not a correctness requirement.

Structured logging is used throughout so cache events appear in the
same log stream as pipeline events.
"""

from __future__ import annotations

import logging

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


async def cache_get(
    redis: aioredis.Redis,  # type: ignore[type-arg]
    key: str,
) -> str | None:
    """Retrieve a value from Redis.

    Returns the cached string on a hit, or None on a miss or any Redis error.
    Never raises — fail-open means the caller proceeds without cached data.
    """
    try:
        value: bytes | str | None = await redis.get(key)
        if value is None:
            logger.debug("Cache miss", extra={"key": key})
            return None
        result = value.decode() if isinstance(value, bytes) else value
        logger.debug("Cache hit", extra={"key": key})
        return result
    except Exception as exc:  # — intentional fail-open
        logger.warning(
            "Cache get error; returning None (fail-open)",
            extra={"key": key, "error": str(exc)},
        )
        return None


async def cache_set(
    redis: aioredis.Redis,  # type: ignore[type-arg]
    key: str,
    value: str,
    ttl_seconds: int,
) -> None:
    """Store a value in Redis with a TTL.

    Swallows all Redis errors and logs a warning so callers are never blocked
    by a cache write failure.
    """
    try:
        await redis.set(key, value, ex=ttl_seconds)
        logger.debug("Cache set", extra={"key": key, "ttl_seconds": ttl_seconds})
    except Exception as exc:  # — intentional fail-open
        logger.warning(
            "Cache set error; continuing without cache",
            extra={"key": key, "ttl_seconds": ttl_seconds, "error": str(exc)},
        )


async def cache_delete(
    redis: aioredis.Redis,  # type: ignore[type-arg]
    key: str,
) -> None:
    """Delete a key from Redis.

    Swallows all Redis errors — a failed delete is non-fatal; the key will
    expire naturally via TTL.
    """
    try:
        await redis.delete(key)
        logger.debug("Cache delete", extra={"key": key})
    except Exception as exc:  # — intentional fail-open
        logger.warning(
            "Cache delete error; key will expire via TTL",
            extra={"key": key, "error": str(exc)},
        )
