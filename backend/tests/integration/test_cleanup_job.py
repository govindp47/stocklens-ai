"""Integration tests for the TTL cleanup job (T-042).

Test cases from 09_TESTING_STRATEGY.md Section 6:
  - test_soft_deletes_runs_older_than_24h
  - test_hard_deletes_soft_deleted_after_grace_period
  - test_does_not_soft_delete_recent_runs
  - test_deletes_expired_ticker_cache_rows
  - test_deletes_old_rate_limit_log_rows

All tests call run_cleanup_once() — the single-cycle test-friendly entry point.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import asyncpg
import pytest

from app.jobs.cleanup import run_cleanup_once


# ── Helpers ────────────────────────────────────────────────────────────────────


async def _insert_run(
    db_pool: asyncpg.Pool,  # type: ignore[type-arg]
    *,
    run_id=None,
    ticker: str = "AAPL",
    status: str = "complete",
    created_at: datetime | None = None,
    is_deleted: bool = False,
    deleted_at: datetime | None = None,
) -> None:
    if run_id is None:
        run_id = uuid4()
    created_at = created_at or datetime.now(tz=UTC)
    async with db_pool.acquire() as conn:  # type: ignore[attr-defined]
        await conn.execute(
            """
            INSERT INTO analysis_runs
                (run_id, ticker, status, llm_provider, steps_total, steps_completed,
                 steps_failed, created_at, is_deleted, deleted_at)
            VALUES ($1, $2, $3, 'ollama', 9, 9, 0, $4, $5, $6)
            """,
            run_id, ticker, status, created_at, is_deleted, deleted_at,
        )
    return run_id


# ── Tests ──────────────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestSoftDeletion:

    async def test_soft_deletes_runs_older_than_24h(
        self,
        db_pool: asyncpg.Pool,  # type: ignore[type-arg]
    ) -> None:
        """Runs with created_at > 24h ago are soft-deleted (is_deleted=True)."""
        old_run_id = uuid4()
        old_time = datetime.now(tz=UTC) - timedelta(hours=25)
        await _insert_run(db_pool, run_id=old_run_id, created_at=old_time)

        counts = await run_cleanup_once(db_pool)

        assert counts["soft_deleted"] >= 1
        async with db_pool.acquire() as conn:  # type: ignore[attr-defined]
            row = await conn.fetchrow(
                "SELECT is_deleted, deleted_at FROM analysis_runs WHERE run_id = $1",
                old_run_id,
            )
        assert row is not None
        assert row["is_deleted"] is True
        assert row["deleted_at"] is not None

    async def test_does_not_soft_delete_recent_runs(
        self,
        db_pool: asyncpg.Pool,  # type: ignore[type-arg]
    ) -> None:
        """Recent runs (created < 24h ago) must NOT be soft-deleted."""
        recent_run_id = uuid4()
        recent_time = datetime.now(tz=UTC) - timedelta(hours=10)
        await _insert_run(db_pool, run_id=recent_run_id, created_at=recent_time)

        counts = await run_cleanup_once(db_pool)

        async with db_pool.acquire() as conn:  # type: ignore[attr-defined]
            row = await conn.fetchrow(
                "SELECT is_deleted FROM analysis_runs WHERE run_id = $1",
                recent_run_id,
            )
        assert row is not None
        assert row["is_deleted"] is False


@pytest.mark.integration
class TestHardDeletion:

    async def test_hard_deletes_soft_deleted_after_grace_period(
        self,
        db_pool: asyncpg.Pool,  # type: ignore[type-arg]
    ) -> None:
        """Runs soft-deleted > 1 hour ago are hard-deleted."""
        run_id = uuid4()
        old_created = datetime.now(tz=UTC) - timedelta(hours=26)
        old_deleted = datetime.now(tz=UTC) - timedelta(hours=2)
        await _insert_run(
            db_pool,
            run_id=run_id,
            created_at=old_created,
            is_deleted=True,
            deleted_at=old_deleted,
        )

        counts = await run_cleanup_once(db_pool)

        assert counts["hard_deleted"] >= 1
        async with db_pool.acquire() as conn:  # type: ignore[attr-defined]
            row = await conn.fetchrow(
                "SELECT run_id FROM analysis_runs WHERE run_id = $1",
                run_id,
            )
        assert row is None, "Row should have been hard-deleted"

    async def test_does_not_hard_delete_recently_soft_deleted(
        self,
        db_pool: asyncpg.Pool,  # type: ignore[type-arg]
    ) -> None:
        """Runs soft-deleted within the 1-hour grace period must NOT be hard-deleted."""
        run_id = uuid4()
        old_created = datetime.now(tz=UTC) - timedelta(hours=25)
        recent_deleted = datetime.now(tz=UTC) - timedelta(minutes=30)
        await _insert_run(
            db_pool,
            run_id=run_id,
            created_at=old_created,
            is_deleted=True,
            deleted_at=recent_deleted,
        )

        counts = await run_cleanup_once(db_pool)

        async with db_pool.acquire() as conn:  # type: ignore[attr-defined]
            row = await conn.fetchrow(
                "SELECT run_id FROM analysis_runs WHERE run_id = $1",
                run_id,
            )
        assert row is not None, "Row within grace period should NOT be hard-deleted"


@pytest.mark.integration
class TestTickerCacheCleanup:

    async def test_deletes_expired_ticker_cache_rows(
        self,
        db_pool: asyncpg.Pool,  # type: ignore[type-arg]
    ) -> None:
        """Expired ticker_resolution_cache rows are deleted."""
        async with db_pool.acquire() as conn:  # type: ignore[attr-defined]
            await conn.execute(
                """
                INSERT INTO ticker_resolution_cache
                    (ticker, is_resolvable, resolved_at, expires_at)
                VALUES ('EXPD', TRUE, NOW() - INTERVAL '2 hours', NOW() - INTERVAL '1 hour')
                """
            )

        counts = await run_cleanup_once(db_pool)

        assert counts["ticker_cache_expired"] >= 1
        async with db_pool.acquire() as conn:  # type: ignore[attr-defined]
            row = await conn.fetchrow(
                "SELECT ticker FROM ticker_resolution_cache WHERE ticker = 'EXPD'"
            )
        assert row is None, "Expired ticker cache row should have been deleted"

    async def test_does_not_delete_valid_ticker_cache_rows(
        self,
        db_pool: asyncpg.Pool,  # type: ignore[type-arg]
    ) -> None:
        """Non-expired ticker_resolution_cache rows must NOT be deleted."""
        async with db_pool.acquire() as conn:  # type: ignore[attr-defined]
            await conn.execute(
                """
                INSERT INTO ticker_resolution_cache
                    (ticker, is_resolvable, resolved_at, expires_at)
                VALUES ('LIVE', TRUE, NOW(), NOW() + INTERVAL '1 hour')
                """
            )

        await run_cleanup_once(db_pool)

        async with db_pool.acquire() as conn:  # type: ignore[attr-defined]
            row = await conn.fetchrow(
                "SELECT ticker FROM ticker_resolution_cache WHERE ticker = 'LIVE'"
            )
        assert row is not None, "Non-expired ticker cache row should still exist"


@pytest.mark.integration
class TestRateLimitLogCleanup:

    async def test_deletes_old_rate_limit_log_rows(
        self,
        db_pool: asyncpg.Pool,  # type: ignore[type-arg]
    ) -> None:
        """rate_limit_log rows older than 7 days are deleted."""
        async with db_pool.acquire() as conn:  # type: ignore[attr-defined]
            await conn.execute(
                """
                INSERT INTO rate_limit_log (ip_address, endpoint, rejected_at)
                VALUES ('1.2.3.4', '/api/v1/analyze', NOW() - INTERVAL '8 days')
                """
            )

        counts = await run_cleanup_once(db_pool)

        assert counts["rate_limit_log_pruned"] >= 1

    async def test_keeps_recent_rate_limit_log_rows(
        self,
        db_pool: asyncpg.Pool,  # type: ignore[type-arg]
    ) -> None:
        """rate_limit_log rows within 7 days must NOT be deleted."""
        async with db_pool.acquire() as conn:  # type: ignore[attr-defined]
            row_id = await conn.fetchval(
                """
                INSERT INTO rate_limit_log (ip_address, endpoint, rejected_at)
                VALUES ('5.6.7.8', '/api/v1/analyze', NOW() - INTERVAL '2 days')
                RETURNING id
                """
            )

        await run_cleanup_once(db_pool)

        async with db_pool.acquire() as conn:  # type: ignore[attr-defined]
            row = await conn.fetchrow(
                "SELECT id FROM rate_limit_log WHERE id = $1",
                row_id,
            )
        assert row is not None, "Recent rate-limit log row should NOT be deleted"
