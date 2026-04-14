"""Background cleanup job — TTL-based data retention enforcement.

Runs on a 3600-second (1-hour) schedule as an asyncio.Task launched in
lifespan.py.  Each iteration performs four SQL operations:

  1. Soft-delete runs older than 24 hours (set is_deleted=True, deleted_at=NOW()).
  2. Hard-delete soft-deleted runs older than 25 hours (deleted_at < NOW()-25h).
     Cascades to pipeline_steps via ON DELETE CASCADE.
  3. Delete expired ticker_resolution_cache rows (expires_at < NOW()).
  4. Delete rate_limit_log rows older than 7 days.

All DB operations are wrapped in try/except.  A failure in one operation is
logged and skipped — the remaining operations continue so a single table error
does not block the entire cleanup pass.

run_cleanup_once(db_pool) exposes a single-cycle version for unit tests.
"""

from __future__ import annotations

import asyncio

import asyncpg
import structlog

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# How long a run is retained before soft-deletion (seconds).
_SOFT_DELETE_AFTER_S: int = 24 * 3600

# Grace period after soft-deletion before hard deletion (seconds).
_HARD_DELETE_AFTER_S: int = 3600  # 1 hour

# Rate-limit log retention window (seconds).
_RATE_LIMIT_LOG_RETENTION_S: int = 7 * 24 * 3600

# Sleep between cleanup cycles (seconds).
_CLEANUP_INTERVAL_S: int = 3600


async def run_cleanup_once(db_pool: asyncpg.Pool) -> dict[str, int]:
    """Execute a single cleanup pass.

    Returns a dict with counts of rows affected per operation.
    Exposed for unit testing without the infinite loop.
    """
    log = logger.bind(job="cleanup")
    counts: dict[str, int] = {
        "soft_deleted": 0,
        "hard_deleted": 0,
        "ticker_cache_expired": 0,
        "rate_limit_log_pruned": 0,
    }

    # ── 1. Soft-delete runs older than 24 hours ────────────────────────────
    try:
        async with db_pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE analysis_runs
                SET    is_deleted = TRUE,
                       deleted_at = NOW()
                WHERE  created_at  < NOW() - make_interval(secs => $1)
                  AND  is_deleted  = FALSE
                """,
                float(_SOFT_DELETE_AFTER_S),
            )
            counts["soft_deleted"] = _rowcount(result)
    except asyncpg.PostgresError as exc:
        log.error("Soft-delete step failed", error=str(exc))

    # ── 2. Hard-delete soft-deleted runs older than 25 hours ──────────────
    try:
        async with db_pool.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM analysis_runs
                WHERE  is_deleted = TRUE
                  AND  deleted_at < NOW() - make_interval(secs => $1)
                """,
                float(_HARD_DELETE_AFTER_S),
            )
            counts["hard_deleted"] = _rowcount(result)
    except asyncpg.PostgresError as exc:
        log.error("Hard-delete step failed", error=str(exc))

    # ── 3. Delete expired ticker_resolution_cache rows ────────────────────
    try:
        async with db_pool.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM ticker_resolution_cache
                WHERE  expires_at < NOW()
                """
            )
            counts["ticker_cache_expired"] = _rowcount(result)
    except asyncpg.PostgresError as exc:
        log.error("Ticker cache cleanup step failed", error=str(exc))

    # ── 4. Delete rate_limit_log rows older than 7 days ───────────────────
    try:
        async with db_pool.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM rate_limit_log
                WHERE  rejected_at < NOW() - make_interval(secs => $1)
                """,
                float(_RATE_LIMIT_LOG_RETENTION_S),
            )
            counts["rate_limit_log_pruned"] = _rowcount(result)
    except asyncpg.PostgresError as exc:
        log.error("Rate-limit log cleanup step failed", error=str(exc))

    return counts


async def run_cleanup_job(db_pool: asyncpg.Pool) -> None:
    """Infinite-loop cleanup job; run as asyncio.Task from lifespan.py.

    Each cycle calls run_cleanup_once() and then sleeps for 1 hour.
    asyncio.CancelledError (raised on shutdown) propagates naturally,
    terminating the loop cleanly.

    Any non-Cancelled exception inside run_cleanup_once is already caught
    per-operation; unexpected outer exceptions are logged and the loop
    continues after the standard sleep interval.
    """
    log = logger.bind(job="cleanup")
    log.info("Cleanup job started")

    while True:
        try:
            counts = await run_cleanup_once(db_pool)
            log.info(
                "Cleanup cycle complete",
                soft_deleted=counts["soft_deleted"],
                hard_deleted=counts["hard_deleted"],
                ticker_cache_expired=counts["ticker_cache_expired"],
                rate_limit_log_pruned=counts["rate_limit_log_pruned"],
            )
        except asyncio.CancelledError:
            log.info("Cleanup job cancelled")
            raise
        except Exception as exc:
            log.error("Unexpected cleanup error", error=str(exc), exc_info=True)

        try:
            await asyncio.sleep(_CLEANUP_INTERVAL_S)
        except asyncio.CancelledError:
            log.info("Cleanup job cancelled during sleep")
            raise


def _rowcount(result: str) -> int:
    """Parse asyncpg command status string like 'DELETE 5' → 5."""
    try:
        return int(result.split()[-1])
    except (ValueError, IndexError):
        return 0
