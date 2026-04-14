"""Background metrics aggregation job — hourly pipeline stats.

Runs on a 300-second (5-minute) schedule as an asyncio.Task launched in
lifespan.py.  Each iteration aggregates analysis_runs data into
system_metrics_hourly for the *current* and *previous* hour buckets.

Re-aggregating the current hour on every cycle means the metrics for the
live hour are always up-to-date.  Re-aggregating the previous hour on every
cycle ensures any late-arriving rows are captured.

run_metrics_aggregation_once(db_pool) exposes a single-cycle version for
unit tests.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
import structlog

from app.infrastructure.repositories.metrics_repository import MetricsRepository

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# Sleep between aggregation cycles (seconds).
_AGGREGATION_INTERVAL_S: int = 300


def _hour_bucket(dt: datetime) -> tuple[datetime, datetime]:
    """Return (bucket_start, bucket_end) for the hour containing dt."""
    start = dt.replace(minute=0, second=0, microsecond=0, tzinfo=UTC)
    end = start + timedelta(hours=1)
    return start, end


async def _aggregate_bucket(
    conn: asyncpg.Connection,
    bucket_start: datetime,
    bucket_end: datetime,
) -> dict[str, Any]:
    """Compute metrics for one hour bucket from analysis_runs.

    Returns a dict matching MetricsRepository.upsert_hourly_metrics kwargs.
    """
    sql = """
        SELECT
            COUNT(*)                                              AS runs_total,
            COUNT(*) FILTER (WHERE status = 'complete')          AS runs_complete,
            COUNT(*) FILTER (WHERE status = 'failed')            AS runs_failed,
            COUNT(*) FILTER (WHERE status = 'timed_out')         AS runs_timed_out,
            COUNT(DISTINCT ticker)                                AS unique_tickers,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY duration_ms)
                                                                  AS p50_duration_ms,
            PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms)
                                                                  AS p95_duration_ms,
            PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY duration_ms)
                                                                  AS p99_duration_ms
        FROM  analysis_runs
        WHERE created_at >= $1
          AND created_at <  $2
    """
    row = await conn.fetchrow(sql, bucket_start, bucket_end)

    # Per-step failure counts
    step_sql = """
        SELECT ps.step_name, COUNT(*) AS failures
        FROM   pipeline_steps ps
        JOIN   analysis_runs  ar ON ar.run_id = ps.run_id
        WHERE  ar.created_at >= $1
          AND  ar.created_at <  $2
          AND  ps.status = 'failed'
        GROUP BY ps.step_name
    """
    step_rows = await conn.fetch(step_sql, bucket_start, bucket_end)
    step_failures: dict[str, int] = {r["step_name"]: r["failures"] for r in step_rows}

    # Rate limit hits in this bucket
    rl_sql = """
        SELECT COUNT(*) AS hits
        FROM   rate_limit_log
        WHERE  rejected_at >= $1
          AND  rejected_at <  $2
    """
    rl_row = await conn.fetchrow(rl_sql, bucket_start, bucket_end)

    def _int_or_none(val: Any) -> int | None:
        return int(val) if val is not None else None

    return {
        "runs_total": int(row["runs_total"] or 0),
        "runs_complete": int(row["runs_complete"] or 0),
        "runs_failed": int(row["runs_failed"] or 0),
        "runs_timed_out": int(row["runs_timed_out"] or 0),
        "unique_tickers": int(row["unique_tickers"] or 0),
        "p50_duration_ms": _int_or_none(row["p50_duration_ms"]),
        "p95_duration_ms": _int_or_none(row["p95_duration_ms"]),
        "p99_duration_ms": _int_or_none(row["p99_duration_ms"]),
        "avg_articles_per_run": None,  # not tracked at DB level
        "rate_limit_hits": int(rl_row["hits"] or 0),
        "step_failures_json": step_failures if step_failures else None,
    }


async def run_metrics_aggregation_once(db_pool: asyncpg.Pool) -> None:
    """Compute and upsert metrics for the current and previous hour buckets.

    Exposed for unit testing without the infinite loop.
    """
    log = logger.bind(job="metrics_aggregator")
    now = datetime.now(tz=UTC)
    repo = MetricsRepository(db_pool)

    for offset_hours in (0, 1):
        bucket_dt = now - timedelta(hours=offset_hours)
        bucket_start, bucket_end = _hour_bucket(bucket_dt)

        try:
            async with db_pool.acquire() as conn:
                kwargs = await _aggregate_bucket(conn, bucket_start, bucket_end)

            await repo.upsert_hourly_metrics(
                bucket_start=bucket_start,
                bucket_end=bucket_end,
                **kwargs,
            )
            log.debug(
                "Metrics upserted",
                bucket_start=bucket_start.isoformat(),
                runs_total=kwargs["runs_total"],
            )
        except Exception as exc:
            log.error(
                "Metrics aggregation failed for bucket",
                bucket_start=bucket_start.isoformat(),
                error=str(exc),
                exc_info=True,
            )


async def run_metrics_aggregation_job(db_pool: asyncpg.Pool) -> None:
    """Infinite-loop metrics aggregation job; run as asyncio.Task from lifespan.py.

    Each cycle calls run_metrics_aggregation_once() and then sleeps 5 minutes.
    asyncio.CancelledError propagates naturally to terminate on shutdown.
    """
    log = logger.bind(job="metrics_aggregator")
    log.info("Metrics aggregation job started")

    while True:
        try:
            await run_metrics_aggregation_once(db_pool)
        except asyncio.CancelledError:
            log.info("Metrics aggregation job cancelled")
            raise
        except Exception as exc:
            log.error(
                "Unexpected metrics aggregation error",
                error=str(exc),
                exc_info=True,
            )

        try:
            await asyncio.sleep(_AGGREGATION_INTERVAL_S)
        except asyncio.CancelledError:
            log.info("Metrics aggregation job cancelled during sleep")
            raise
