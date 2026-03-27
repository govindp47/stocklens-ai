"""RateLimitRepository — append-only audit log for rate limit rejections.

The enforcement mechanism itself is Redis-based (sliding window, implemented in
T-027). This repository records durable audit rows in rate_limit_log for abuse
detection and threshold tuning. It does NOT enforce rate limits.

log_rejection is safe to call multiple times for the same IP; each call inserts
a new row (the table is append-only by design, with no UNIQUE constraint).
"""

from __future__ import annotations

import logging

import asyncpg

logger = logging.getLogger(__name__)


class RateLimitRepository:
    """Append-only writer for the rate_limit_log audit table."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def log_rejection(
        self,
        ip_address: str,
        endpoint: str,
        *,
        window_count: int | None = None,
        window_seconds: int | None = None,
    ) -> None:
        """Insert a rate-limit rejection audit record.

        Never raises on duplicate calls for the same IP — each call creates a
        new row, which is correct because each rejection is a distinct event.
        """
        sql = """
            INSERT INTO rate_limit_log
                (ip_address, endpoint, rejected_at, window_count, window_seconds)
            VALUES
                ($1, $2, NOW(), $3, $4)
        """
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(sql, ip_address, endpoint, window_count, window_seconds)
        except asyncpg.PostgresError as exc:
            # Log but do not re-raise: a failure to write audit data must never
            # block the rate-limit rejection response to the client.
            logger.error(
                "Failed to write rate limit audit log: %s",
                exc,
                extra={"ip_address": ip_address, "endpoint": endpoint},
            )
