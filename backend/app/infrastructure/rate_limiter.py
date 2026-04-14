"""RedisSlidingWindowRateLimiter — atomic sliding-window rate limiter.

Algorithm (per-IP, per-endpoint sorted set):
  1. ZREMRANGEBYSCORE key 0 window_start   — evict expired members
  2. ZADD key score member                 — record current request
  3. ZCARD key                             — count members in window
  4. EXPIRE key (window + 1)              — auto-cleanup

All four commands execute in a single Redis pipeline (transaction=True) so
the state observed by ZCARD is consistent with the preceding writes.

Security: the raw client IP is never stored in a Redis key.  Keys use the
first 16 hex characters of the SHA-256 hash of the IP address.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from typing import Protocol

import redis.asyncio as aioredis

from app.config import get_settings

logger = logging.getLogger(__name__)

# ── Per-endpoint limit table (from 07_SECURITY_MODEL.md § 9.1) ────────────────
# Key format: "{method}_{path_slug}"  (produced by endpoint_slug())
_ENDPOINT_LIMITS: dict[str, int] = {
    "post_analyze": 10,  # POST /api/v1/analyze  — expensive LLM pipeline
    "get_analyze": 100,  # GET  /api/v1/analyze/* — status/report polling
    "get_health": 300,  # GET  /health
    "default": 100,  # fallback for unlisted endpoints
}


# ── Protocol ──────────────────────────────────────────────────────────────────


class RateLimiter(Protocol):
    """Sliding-window rate limiter interface.

    check() is the only method callers invoke. It is designed to be called
    in the FastAPI middleware layer before any business logic executes.
    """

    async def check(self, ip: str, endpoint: str) -> tuple[bool, int]:
        """Check whether the request is within the rate limit window.

        Args:
            ip:       Client IP address (used as the sliding window key).
            endpoint: The API endpoint being requested (e.g. 'POST /api/v1/analyze').

        Returns:
            A tuple of (allowed, current_count) where:
              - allowed       is True if the request may proceed.
              - current_count is the number of requests seen in the current window.
        """
        ...


# ── Helpers ───────────────────────────────────────────────────────────────────


def _hash_ip(ip: str) -> str:
    """Return the first 16 hex characters of SHA-256(ip).

    Raw IPs are never embedded in Redis keys — only the truncated hash.
    """
    return hashlib.sha256(ip.encode()).hexdigest()[:16]


def endpoint_slug(endpoint: str) -> str:
    """Convert an endpoint string to a safe Redis key component.

    Examples::
        "POST /api/v1/analyze"       → "post_analyze"
        "GET /api/v1/analyze/abc123" → "get_analyze"
        "GET /health"                → "get_health"
    """
    parts = endpoint.strip().split(None, 1)
    method = parts[0].lower() if parts else "get"
    path = parts[1] if len(parts) > 1 else "/"

    # Strip leading slash, then optional "api/vN/" version prefix
    path_no_slash = path.lstrip("/")
    path_clean = re.sub(r"^api/v\d+/", "", path_no_slash)
    slug = re.split(r"[/\s]", path_clean)[0] or "root"

    return f"{method}_{slug}"


def _limit_for(slug: str) -> int:
    """Return the configured request limit for the given endpoint slug."""
    return _ENDPOINT_LIMITS.get(slug, _ENDPOINT_LIMITS["default"])


# ── Implementation ────────────────────────────────────────────────────────────


class RedisSlidingWindowRateLimiter:
    """Redis-backed sliding window rate limiter using sorted sets.

    Each (IP hash, endpoint) pair has its own sorted set key.  Timestamps
    serve as both the member score and the member value (stringified
    nanoseconds) so concurrent requests in the same millisecond are
    distinguished by appending a unique sub-identifier.

    Configuration is read from Settings on every instantiation so that
    tests can inject a custom settings object via the constructor.
    """

    def __init__(
        self,
        redis: aioredis.Redis,  # type: ignore[type-arg]
        window_seconds: int | None = None,
    ) -> None:
        self._redis = redis
        settings = get_settings()
        self._window: int = (
            window_seconds if window_seconds is not None else settings.rate_limit_window_seconds
        )

    async def check(self, ip: str, endpoint: str) -> tuple[bool, int]:
        """Atomically check and record a request against the sliding window.

        Returns:
            (True,  count) — request is within the limit; may proceed.
            (False, count) — request exceeds the limit; should be rejected.
        """
        slug = endpoint_slug(endpoint)
        limit = _limit_for(slug)
        ip_hash = _hash_ip(ip)
        key = f"rl:{ip_hash}:{slug}"

        now_ns = time.time_ns()
        now_score = float(now_ns)
        window_start = float(now_ns - self._window * 1_000_000_000)
        # Use nanosecond timestamp as unique member so concurrent requests
        # from the same IP within the same millisecond don't collide.
        member = str(now_ns)

        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                # 1. Remove members whose score < window_start (expired)
                pipe.zremrangebyscore(key, 0, window_start)
                # 2. Add current request
                pipe.zadd(key, {member: now_score})
                # 3. Count members in window
                pipe.zcard(key)
                # 4. Auto-expire key slightly past the window
                pipe.expire(key, self._window + 1)
                results = await pipe.execute()

            count: int = int(results[2])
            allowed = count <= limit
            logger.debug(
                "Rate limit check",
                extra={
                    "key": key,
                    "count": count,
                    "limit": limit,
                    "allowed": allowed,
                },
            )
            return allowed, count

        except Exception as exc:
            # Fail-open: a Redis error must not block legitimate traffic.
            logger.warning(
                "Rate limiter Redis error; allowing request (fail-open)",
                extra={"key": key, "error": str(exc)},
            )
            return True, 0
