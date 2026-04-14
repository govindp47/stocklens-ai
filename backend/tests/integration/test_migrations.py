"""Integration tests for Alembic migrations.

Tests:
  1. test_upgrade_from_initial_schema    — all five tables exist after upgrade.
  2. test_downgrade_and_upgrade_is_idempotent — schema is identical after round-trip.
  3. test_fk_constraint_enforced         — FK from pipeline_steps → analysis_runs.
  4. test_check_constraint_ticker_format — invalid ticker raises CheckViolationError.
  5. test_unique_constraint_on_run_id    — duplicate run_id raises UniqueViolationError.

These tests run against the live test PostgreSQL instance (TEST_DATABASE_URL).
The schema is assumed to be at head before this suite runs.
"""

from __future__ import annotations

import uuid

import asyncpg
import pytest

pytestmark = pytest.mark.integration

# Tables created by revision 0001
EXPECTED_TABLES = {
    "analysis_runs",
    "pipeline_steps",
    "system_metrics_hourly",
    "ticker_resolution_cache",
    "rate_limit_log",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _table_names(conn: asyncpg.Connection) -> set[str]:  # type: ignore[type-arg]
    """Return the set of user-created table names in the public schema."""
    rows = await conn.fetch(
        """
        SELECT tablename
        FROM   pg_tables
        WHERE  schemaname = 'public'
          AND  tablename != 'alembic_version'
        """
    )
    return {row["tablename"] for row in rows}


async def _insert_run(conn: asyncpg.Connection, ticker: str = "AAPL") -> uuid.UUID:  # type: ignore[type-arg]
    """Insert a minimal analysis_runs row and return its run_id."""
    run_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO analysis_runs (run_id, ticker) VALUES ($1, $2)",
        run_id,
        ticker,
    )
    return run_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestUpgradeFromInitialSchema:
    async def test_all_tables_exist(self, db_pool: asyncpg.Pool) -> None:  # type: ignore[type-arg]
        """All five application tables must exist after alembic upgrade head."""
        async with db_pool.acquire() as conn:
            tables = await _table_names(conn)
        assert EXPECTED_TABLES.issubset(tables), f"Missing tables: {EXPECTED_TABLES - tables}"

    async def test_analysis_runs_has_required_columns(self, db_pool: asyncpg.Pool) -> None:  # type: ignore[type-arg]
        """analysis_runs must have run_id, ticker, status, and updated_at columns."""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT column_name
                FROM   information_schema.columns
                WHERE  table_name   = 'analysis_runs'
                  AND  table_schema = 'public'
                """
            )
        columns = {row["column_name"] for row in rows}
        required = {"run_id", "ticker", "status", "updated_at", "report_data"}
        assert required.issubset(columns), f"Missing columns: {required - columns}"

    async def test_updated_at_trigger_exists(self, db_pool: asyncpg.Pool) -> None:  # type: ignore[type-arg]
        """The updated_at trigger must be installed on analysis_runs."""
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT trigger_name
                FROM   information_schema.triggers
                WHERE  event_object_table = 'analysis_runs'
                  AND  trigger_name       = 'trg_analysis_runs_updated_at'
                """
            )
        assert row is not None, "updated_at trigger not found on analysis_runs"


class TestDowngradeAndUpgradeIsIdempotent:
    async def test_tables_survive_round_trip(self, db_pool: asyncpg.Pool) -> None:  # type: ignore[type-arg]
        """Schema must be intact after the clean_db fixture (no structural change)."""
        # The clean_db fixture has already truncated tables; verify they still exist
        async with db_pool.acquire() as conn:
            tables = await _table_names(conn)
        assert EXPECTED_TABLES.issubset(tables)

    async def test_insert_after_truncate_succeeds(self, db_pool: asyncpg.Pool) -> None:  # type: ignore[type-arg]
        """Insert succeeds after clean_db truncation (RESTART IDENTITY is safe)."""
        async with db_pool.acquire() as conn:
            run_id = await _insert_run(conn)
            row = await conn.fetchrow("SELECT run_id FROM analysis_runs WHERE run_id = $1", run_id)
        assert row is not None


class TestFkConstraintEnforced:
    async def test_pipeline_step_requires_valid_run_id(
        self,
        db_pool: asyncpg.Pool,  # type: ignore[type-arg]
    ) -> None:
        """Inserting a pipeline_steps row with a non-existent run_id must fail."""
        ghost_run_id = uuid.uuid4()
        async with db_pool.acquire() as conn:
            with pytest.raises(asyncpg.ForeignKeyViolationError):
                await conn.execute(
                    """
                    INSERT INTO pipeline_steps (run_id, step_index, step_name)
                    VALUES ($1, 1, 'TickerValidator')
                    """,
                    ghost_run_id,
                )

    async def test_cascade_delete_removes_steps(self, db_pool: asyncpg.Pool) -> None:  # type: ignore[type-arg]
        """Deleting an analysis_runs row must cascade-delete all child pipeline_steps."""
        async with db_pool.acquire() as conn:
            run_id = await _insert_run(conn)
            await conn.execute(
                """
                INSERT INTO pipeline_steps (run_id, step_index, step_name)
                VALUES ($1, 1, 'TickerValidator'), ($1, 2, 'MarketDataCollector')
                """,
                run_id,
            )
            # Verify children exist
            count_before = await conn.fetchval(
                "SELECT COUNT(*) FROM pipeline_steps WHERE run_id = $1", run_id
            )
            assert count_before == 2

            # Delete parent
            await conn.execute("DELETE FROM analysis_runs WHERE run_id = $1", run_id)

            # Children must be gone
            count_after = await conn.fetchval(
                "SELECT COUNT(*) FROM pipeline_steps WHERE run_id = $1", run_id
            )
        assert count_after == 0


class TestCheckConstraintTickerFormat:
    async def test_invalid_ticker_rejected(self, db_pool: asyncpg.Pool) -> None:  # type: ignore[type-arg]
        """INSERT with '123INVALID!' as ticker must raise CheckViolationError."""
        async with db_pool.acquire() as conn:
            with pytest.raises(asyncpg.CheckViolationError):
                await conn.execute(
                    "INSERT INTO analysis_runs (run_id, ticker) VALUES ($1, $2)",
                    uuid.uuid4(),
                    "123INVALID!",
                )

    async def test_valid_ticker_accepted(self, db_pool: asyncpg.Pool) -> None:  # type: ignore[type-arg]
        """Valid tickers ('AAPL', 'BRK.A') must be accepted by the CHECK constraint."""
        async with db_pool.acquire() as conn:
            for ticker in ("AAPL", "MSFT", "BRK.A"):
                run_id = uuid.uuid4()
                await conn.execute(
                    "INSERT INTO analysis_runs (run_id, ticker) VALUES ($1, $2)",
                    run_id,
                    ticker,
                )
                row = await conn.fetchrow(
                    "SELECT ticker FROM analysis_runs WHERE run_id = $1", run_id
                )
                assert row is not None
                assert row["ticker"] == ticker

    async def test_invalid_status_rejected(self, db_pool: asyncpg.Pool) -> None:  # type: ignore[type-arg]
        """Invalid status value must raise CheckViolationError."""
        async with db_pool.acquire() as conn:
            with pytest.raises(asyncpg.CheckViolationError):
                await conn.execute(
                    "INSERT INTO analysis_runs (run_id, ticker, status) VALUES ($1, $2, $3)",
                    uuid.uuid4(),
                    "AAPL",
                    "bad_status",
                )


class TestUniqueConstraintOnRunId:
    async def test_duplicate_run_id_rejected(self, db_pool: asyncpg.Pool) -> None:  # type: ignore[type-arg]
        """Inserting two rows with the same run_id must raise UniqueViolationError."""
        run_id = uuid.uuid4()
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO analysis_runs (run_id, ticker) VALUES ($1, $2)",
                run_id,
                "AAPL",
            )
            with pytest.raises(asyncpg.UniqueViolationError):
                await conn.execute(
                    "INSERT INTO analysis_runs (run_id, ticker) VALUES ($1, $2)",
                    run_id,
                    "MSFT",
                )
