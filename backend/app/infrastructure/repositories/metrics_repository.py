"""MetricsRepository — system_metrics_hourly read/write operations.

upsert_hourly_metrics is idempotent: ON CONFLICT (bucket_start) DO UPDATE SET
overwrites all metric columns so re-running the metrics job for the same hour
produces a consistent result without duplicates.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import asyncpg

from app.domain.exceptions import ExternalProviderError

logger = logging.getLogger(__name__)


class MetricsRepository:
    """Data-access object for hourly system metrics aggregation."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def upsert_hourly_metrics(
        self,
        bucket_start: datetime,
        bucket_end: datetime,
        *,
        runs_total: int = 0,
        runs_complete: int = 0,
        runs_failed: int = 0,
        runs_timed_out: int = 0,
        p50_duration_ms: int | None = None,
        p95_duration_ms: int | None = None,
        p99_duration_ms: int | None = None,
        unique_tickers: int = 0,
        avg_articles_per_run: float | None = None,
        rate_limit_hits: int = 0,
        step_failures_json: dict[str, int] | None = None,
    ) -> None:
        """Insert or update the metrics row for the given hour bucket.

        Idempotent: a second call for the same bucket_start overwrites all
        columns rather than creating a duplicate row.
        """
        step_failures_str = json.dumps(step_failures_json) if step_failures_json else None

        sql = """
            INSERT INTO system_metrics_hourly
                (bucket_start, bucket_end,
                 runs_total, runs_complete, runs_failed, runs_timed_out,
                 p50_duration_ms, p95_duration_ms, p99_duration_ms,
                 unique_tickers, avg_articles_per_run,
                 rate_limit_hits, step_failures_json)
            VALUES
                ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13::jsonb)
            ON CONFLICT (bucket_start)
            DO UPDATE SET
                bucket_end           = EXCLUDED.bucket_end,
                runs_total           = EXCLUDED.runs_total,
                runs_complete        = EXCLUDED.runs_complete,
                runs_failed          = EXCLUDED.runs_failed,
                runs_timed_out       = EXCLUDED.runs_timed_out,
                p50_duration_ms      = EXCLUDED.p50_duration_ms,
                p95_duration_ms      = EXCLUDED.p95_duration_ms,
                p99_duration_ms      = EXCLUDED.p99_duration_ms,
                unique_tickers       = EXCLUDED.unique_tickers,
                avg_articles_per_run = EXCLUDED.avg_articles_per_run,
                rate_limit_hits      = EXCLUDED.rate_limit_hits,
                step_failures_json   = EXCLUDED.step_failures_json,
                recorded_at          = NOW()
        """
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    sql,
                    bucket_start,
                    bucket_end,
                    runs_total,
                    runs_complete,
                    runs_failed,
                    runs_timed_out,
                    p50_duration_ms,
                    p95_duration_ms,
                    p99_duration_ms,
                    unique_tickers,
                    avg_articles_per_run,
                    rate_limit_hits,
                    step_failures_str,
                )
        except asyncpg.PostgresError as exc:
            raise ExternalProviderError(
                f"Failed to upsert hourly metrics for {bucket_start}: {exc}",
                error_code="DB_METRICS_UPSERT_ERROR",
                user_message="Failed to record system metrics.",
                is_retryable=True,
            ) from exc

    async def get_recent_metrics(self, hours: int = 24) -> list[dict[str, Any]]:
        """Return the most recent `hours` metric rows, newest first.

        Used by the GET /api/v1/metrics endpoint.
        """
        sql = """
            SELECT
                bucket_start, bucket_end,
                runs_total, runs_complete, runs_failed, runs_timed_out,
                p50_duration_ms, p95_duration_ms, p99_duration_ms,
                unique_tickers, avg_articles_per_run,
                rate_limit_hits, step_failures_json,
                recorded_at
            FROM   system_metrics_hourly
            WHERE  bucket_start >= NOW() - make_interval(hours => $1)
            ORDER  BY bucket_start DESC
        """
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(sql, hours)
            return [dict(row) for row in rows]
        except asyncpg.PostgresError as exc:
            raise ExternalProviderError(
                f"Failed to fetch recent metrics: {exc}",
                error_code="DB_METRICS_FETCH_ERROR",
                user_message="Failed to retrieve system metrics.",
                is_retryable=True,
            ) from exc
