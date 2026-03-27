"""RateLimiter Protocol and stub Redis implementation.

The full RedisSlidingWindowRateLimiter (atomic Lua script, pipeline execution,
Redis key expiry) is implemented in T-027.

At this stage the Protocol is defined so that all type-checked code that
references RateLimiter as a dependency injection target can be checked by mypy.
"""

from __future__ import annotations

from typing import Protocol


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


class RedisSlidingWindowRateLimiter:
    """Redis-backed sliding window rate limiter — full implementation in T-027.

    This stub satisfies the RateLimiter Protocol so it can be wired into
    the dependency injection container before T-027 is complete.
    """

    # TODO: T-027 — implement atomic Lua sliding window with Redis pipeline

    async def check(self, ip: str, endpoint: str) -> tuple[bool, int]:
        """Stub: always allows requests until T-027 is implemented."""
        return True, 0
