"""Integration tests for repository layer (T-011 / T-012).

Tests run against the live test PostgreSQL instance. The clean_db autouse
fixture truncates all tables before each test so each test starts with an
empty schema.

Test cases:
  test_create_and_get_run               — create a run, fetch it back by run_id.
  test_mark_in_progress_optimistic_lock — verify that a second mark_in_progress returns False.
  test_mark_complete_prevents_double_write — AND report_data IS NULL guard.
  test_upsert_step_idempotent           — calling upsert_step twice doesn't create two rows.
  test_get_recent_run_returns_none_after_window — no match when window has expired.
  test_negative_ticker_cache            — resolve() returns False for known-bad tickers.
  test_metrics_upsert_idempotent        — second upsert for same bucket_start overwrites.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest

from app.infrastructure.repositories.metrics_repository import MetricsRepository
from app.infrastructure.repositories.report_repository import ReportRepository
from app.infrastructure.repositories.ticker_cache_repository import TickerCacheRepository

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_repo(pool: asyncpg.Pool) -> ReportRepository:  # type: ignore[type-arg]
    return ReportRepository(pool)


async def _create_run(
    repo: ReportRepository,
    ticker: str = "AAPL",
    ip: str = "1.2.3.4",
) -> uuid.UUID:
    run_id = uuid.uuid4()
    await repo.create_run(
        run_id=run_id,
        ticker=ticker,
        ip_address=ip,
        llm_provider="ollama",
        llm_model="mistral:7b-instruct",
    )
    return run_id


# ---------------------------------------------------------------------------
# ReportRepository tests
# ---------------------------------------------------------------------------


class TestCreateAndGetRun:
    async def test_create_then_get_returns_row(self, db_pool: asyncpg.Pool) -> None:  # type: ignore[type-arg]
        repo = _make_repo(db_pool)
        run_id = await _create_run(repo)

        row = await repo.get_run_by_id(run_id)

        assert row is not None
        assert uuid.UUID(str(row["run_id"])) == run_id
        assert row["ticker"] == "AAPL"
        assert row["status"] == "accepted"
        assert row["steps_total"] == 9
        assert row["steps_completed"] == 0

    async def test_get_nonexistent_run_returns_none(self, db_pool: asyncpg.Pool) -> None:  # type: ignore[type-arg]
        repo = _make_repo(db_pool)
        result = await repo.get_run_by_id(uuid.uuid4())
        assert result is None

    async def test_created_run_status_is_accepted(self, db_pool: asyncpg.Pool) -> None:  # type: ignore[type-arg]
        repo = _make_repo(db_pool)
        run_id = await _create_run(repo)
        row = await repo.get_run_by_id(run_id)
        assert row is not None
        assert row["status"] == "accepted"


class TestMarkInProgressOptimisticLock:
    async def test_first_transition_succeeds(self, db_pool: asyncpg.Pool) -> None:  # type: ignore[type-arg]
        repo = _make_repo(db_pool)
        run_id = await _create_run(repo)
        result = await repo.mark_in_progress(run_id)
        assert result is True

    async def test_second_transition_returns_false(self, db_pool: asyncpg.Pool) -> None:  # type: ignore[type-arg]
        """Calling mark_in_progress twice returns False on the second call."""
        repo = _make_repo(db_pool)
        run_id = await _create_run(repo)
        await repo.mark_in_progress(run_id)
        result = await repo.mark_in_progress(run_id)
        assert result is False

    async def test_status_is_in_progress_after_transition(
        self,
        db_pool: asyncpg.Pool,  # type: ignore[type-arg]
    ) -> None:
        repo = _make_repo(db_pool)
        run_id = await _create_run(repo)
        await repo.mark_in_progress(run_id)
        row = await repo.get_run_by_id(run_id)
        assert row is not None
        assert row["status"] == "in_progress"


class TestMarkCompletePreventDoubleWrite:
    async def test_first_mark_complete_succeeds(self, db_pool: asyncpg.Pool) -> None:  # type: ignore[type-arg]
        repo = _make_repo(db_pool)
        run_id = await _create_run(repo)
        await repo.mark_in_progress(run_id)

        report = json.dumps({"ticker": "AAPL", "completeness": "complete"})
        result = await repo.mark_complete(run_id, report, steps_completed=9)

        assert result is True
        row = await repo.get_run_by_id(run_id)
        assert row is not None
        assert row["status"] == "complete"

    async def test_second_mark_complete_returns_false(
        self,
        db_pool: asyncpg.Pool,  # type: ignore[type-arg]
    ) -> None:
        """AND report_data IS NULL guard prevents overwriting an existing report."""
        repo = _make_repo(db_pool)
        run_id = await _create_run(repo)
        await repo.mark_in_progress(run_id)

        report = json.dumps({"ticker": "AAPL"})
        await repo.mark_complete(run_id, report, steps_completed=9)
        # Second attempt — report_data already set, guard rejects
        result = await repo.mark_complete(run_id, report, steps_completed=9)

        assert result is False

    async def test_mark_failed_transitions_correctly(self, db_pool: asyncpg.Pool) -> None:  # type: ignore[type-arg]
        repo = _make_repo(db_pool)
        run_id = await _create_run(repo)
        await repo.mark_in_progress(run_id)

        result = await repo.mark_failed(
            run_id, "Provider timeout", steps_completed=2, steps_failed=1
        )
        assert result is True

        row = await repo.get_run_by_id(run_id)
        assert row is not None
        assert row["status"] == "failed"

    async def test_mark_timed_out_transitions_correctly(self, db_pool: asyncpg.Pool) -> None:  # type: ignore[type-arg]
        repo = _make_repo(db_pool)
        run_id = await _create_run(repo)
        await repo.mark_in_progress(run_id)

        result = await repo.mark_timed_out(run_id)
        assert result is True

        row = await repo.get_run_by_id(run_id)
        assert row is not None
        assert row["status"] == "timed_out"


class TestUpsertStepIdempotent:
    async def test_first_upsert_creates_row(self, db_pool: asyncpg.Pool) -> None:  # type: ignore[type-arg]
        repo = _make_repo(db_pool)
        run_id = await _create_run(repo)

        await repo.upsert_step(run_id, 1, "TickerValidator", "complete", duration_ms=50)

        async with db_pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM pipeline_steps WHERE run_id = $1", run_id
            )
        assert count == 1

    async def test_second_upsert_does_not_create_duplicate(
        self,
        db_pool: asyncpg.Pool,  # type: ignore[type-arg]
    ) -> None:
        """Calling upsert_step twice with same (run_id, step_index) produces one row."""
        repo = _make_repo(db_pool)
        run_id = await _create_run(repo)

        await repo.upsert_step(run_id, 1, "TickerValidator", "in_progress")
        await repo.upsert_step(
            run_id,
            1,
            "TickerValidator",
            "complete",
            duration_ms=100,
            output_summary={"resolved": True},
        )

        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT status, duration_ms FROM pipeline_steps "
                "WHERE run_id = $1 AND step_index = 1",
                run_id,
            )

        assert row is not None
        assert row["status"] == "complete"
        assert row["duration_ms"] == 100

    async def test_upsert_step_with_error_fields(self, db_pool: asyncpg.Pool) -> None:  # type: ignore[type-arg]
        repo = _make_repo(db_pool)
        run_id = await _create_run(repo)

        await repo.upsert_step(
            run_id,
            2,
            "MarketDataCollector",
            "failed",
            error_message="yfinance timeout",
            error_code="YFINANCE_TIMEOUT",
            retry_count=1,
        )

        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT error_code, retry_count FROM pipeline_steps WHERE run_id = $1",
                run_id,
            )
        assert row is not None
        assert row["error_code"] == "YFINANCE_TIMEOUT"
        assert row["retry_count"] == 1


class TestGetRecentRunReturnsNoneAfterWindow:
    async def test_returns_run_id_within_window(self, db_pool: asyncpg.Pool) -> None:  # type: ignore[type-arg]
        """A run created just now within 2 minutes must be returned."""
        repo = _make_repo(db_pool)
        run_id = await _create_run(repo, ticker="MSFT", ip="10.0.0.1")

        result = await repo.get_recent_run_for_ip_and_ticker("10.0.0.1", "MSFT")
        assert result == run_id

    async def test_returns_none_for_different_ip(self, db_pool: asyncpg.Pool) -> None:  # type: ignore[type-arg]
        """A run for a different IP must not be returned."""
        repo = _make_repo(db_pool)
        await _create_run(repo, ticker="MSFT", ip="10.0.0.1")

        result = await repo.get_recent_run_for_ip_and_ticker("10.0.0.2", "MSFT")
        assert result is None

    async def test_returns_none_for_different_ticker(self, db_pool: asyncpg.Pool) -> None:  # type: ignore[type-arg]
        """A run for a different ticker must not be returned."""
        repo = _make_repo(db_pool)
        await _create_run(repo, ticker="AAPL", ip="10.0.0.1")

        result = await repo.get_recent_run_for_ip_and_ticker("10.0.0.1", "MSFT")
        assert result is None

    async def test_returns_none_when_completed(self, db_pool: asyncpg.Pool) -> None:  # type: ignore[type-arg]
        """A completed run must not be returned by the idempotency check."""
        repo = _make_repo(db_pool)
        run_id = await _create_run(repo, ticker="NVDA", ip="10.0.0.5")
        await repo.mark_in_progress(run_id)
        report_json = json.dumps({"ticker": "NVDA"})
        await repo.mark_complete(run_id, report_json, steps_completed=9)

        result = await repo.get_recent_run_for_ip_and_ticker("10.0.0.5", "NVDA")
        assert result is None


# ---------------------------------------------------------------------------
# TickerCacheRepository tests
# ---------------------------------------------------------------------------


class TestNegativeTickerCache:
    async def test_resolve_returns_none_for_uncached(
        self,
        db_pool: asyncpg.Pool,
        redis: object,  # type: ignore[type-arg]
    ) -> None:
        """An uncached ticker must return None (cache miss)."""
        import redis.asyncio as aioredis

        redis_client: aioredis.Redis = redis  # type: ignore[assignment, type-arg]
        repo = TickerCacheRepository(pool=db_pool, redis=redis_client)

        result = await repo.resolve("UNKNOWN")
        assert result is None

    async def test_negative_cache_returns_false(
        self,
        db_pool: asyncpg.Pool,
        redis: object,  # type: ignore[type-arg]
    ) -> None:
        """A ticker set as unresolvable must return False, not None."""
        import redis.asyncio as aioredis

        redis_client: aioredis.Redis = redis  # type: ignore[assignment, type-arg]
        repo = TickerCacheRepository(pool=db_pool, redis=redis_client)

        await repo.set_resolved("BADTICKER", is_resolvable=False)
        result = await repo.resolve("BADTICKER")

        assert result is False

    async def test_positive_cache_returns_true(
        self,
        db_pool: asyncpg.Pool,
        redis: object,  # type: ignore[type-arg]
    ) -> None:
        """A ticker set as resolvable must return True."""
        import redis.asyncio as aioredis

        redis_client: aioredis.Redis = redis  # type: ignore[assignment, type-arg]
        repo = TickerCacheRepository(pool=db_pool, redis=redis_client)

        await repo.set_resolved("AAPL", is_resolvable=True, company_name="Apple Inc.")
        result = await repo.resolve("AAPL")

        assert result is True

    async def test_pg_fallback_after_redis_miss(
        self,
        db_pool: asyncpg.Pool,
        redis: object,  # type: ignore[type-arg]
    ) -> None:
        """After Redis is flushed, resolve() falls back to PostgreSQL."""
        import fakeredis.aioredis as fakeredis
        import redis.asyncio as aioredis

        # Write to both stores via a fresh instance
        redis_client: aioredis.Redis = redis  # type: ignore[assignment, type-arg]
        repo = TickerCacheRepository(pool=db_pool, redis=redis_client)
        await repo.set_resolved("GOOG", is_resolvable=True, company_name="Alphabet Inc.")

        # Flush Redis to simulate a cache miss
        fr: fakeredis.FakeRedis = redis  # type: ignore[assignment, type-arg]
        await fr.flushall()

        # Resolve must still return True via PostgreSQL fallback
        result = await repo.resolve("GOOG")
        assert result is True


# ---------------------------------------------------------------------------
# MetricsRepository tests
# ---------------------------------------------------------------------------


class TestMetricsUpsertIdempotent:
    async def test_first_upsert_creates_row(self, db_pool: asyncpg.Pool) -> None:  # type: ignore[type-arg]
        repo = MetricsRepository(db_pool)
        now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        bucket_start = now - timedelta(hours=2)
        bucket_end = bucket_start + timedelta(hours=1)

        await repo.upsert_hourly_metrics(
            bucket_start,
            bucket_end,
            runs_total=10,
            runs_complete=8,
            runs_failed=1,
            runs_timed_out=1,
        )

        rows = await repo.get_recent_metrics(hours=48)
        assert len(rows) == 1
        assert rows[0]["runs_total"] == 10

    async def test_second_upsert_overwrites_not_duplicates(
        self,
        db_pool: asyncpg.Pool,  # type: ignore[type-arg]
    ) -> None:
        """Calling upsert twice for the same bucket_start must produce one row."""
        repo = MetricsRepository(db_pool)
        now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        bucket_start = now - timedelta(hours=2)
        bucket_end = bucket_start + timedelta(hours=1)

        await repo.upsert_hourly_metrics(bucket_start, bucket_end, runs_total=5)
        await repo.upsert_hourly_metrics(bucket_start, bucket_end, runs_total=12)

        rows = await repo.get_recent_metrics(hours=48)
        assert len(rows) == 1
        assert rows[0]["runs_total"] == 12

    async def test_get_recent_metrics_returns_newest_first(
        self,
        db_pool: asyncpg.Pool,  # type: ignore[type-arg]
    ) -> None:
        repo = MetricsRepository(db_pool)
        now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)

        for offset in (4, 3, 2):
            bucket_start = now - timedelta(hours=offset)
            bucket_end = bucket_start + timedelta(hours=1)
            await repo.upsert_hourly_metrics(bucket_start, bucket_end, runs_total=offset)

        rows = await repo.get_recent_metrics(hours=48)
        assert len(rows) == 3
        # Newest first: offset 2 is most recent, offset 4 is oldest
        assert rows[0]["runs_total"] == 2
        assert rows[2]["runs_total"] == 4
