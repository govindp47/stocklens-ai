"""Unit tests for database least-privilege grants (T-055).

Verifies that the ``stocklens_app`` PostgreSQL role has exactly the rights
specified in 07_SECURITY_MODEL.md §4.3:

* SELECT, INSERT, UPDATE, DELETE on the four mutable application tables.
* SELECT, INSERT only on ``rate_limit_log`` (append-only — no UPDATE/DELETE).
* USAGE, SELECT on all sequences (required for autoincrement INSERTs).
* CREATE on ``public`` schema is REVOKED (no DDL rights).

The test connects directly to PostgreSQL as ``stocklens_app`` using asyncpg
and asserts that a DDL statement raises
``asyncpg.exceptions.InsufficientPrivilegeError``.

Environment variables (with defaults matching the local dev docker-compose):
  APP_DB_USER     — application DB username  (default: stocklens_app)
  APP_DB_PASSWORD — application DB password  (default: apppassword)
  APP_DB_HOST     — DB host                  (default: localhost)
  APP_DB_PORT     — DB port                  (default: 5432)
  APP_DB_NAME     — DB name                  (default: stocklens)
"""

from __future__ import annotations

import os

import asyncpg
import pytest

# ── Connection helper ───────────────────────────────────────────────────────


def _dsn() -> str:
    user = os.getenv("APP_DB_USER", "stocklens_app")
    password = os.getenv("APP_DB_PASSWORD", "apppassword")
    host = os.getenv("APP_DB_HOST", "localhost")
    port = os.getenv("APP_DB_PORT", "5432")
    dbname = os.getenv("APP_DB_NAME", "stocklens")
    return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"


# ── Tests ───────────────────────────────────────────────────────────────────


@pytest.mark.unit()
class TestDatabaseLeastPrivilege:
    """Verify stocklens_app role privilege boundaries."""

    @pytest.mark.asyncio()
    async def test_app_user_cannot_create_table(self) -> None:
        """stocklens_app must raise InsufficientPrivilegeError on CREATE TABLE."""
        conn = await asyncpg.connect(dsn=_dsn())
        try:
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await conn.execute(
                    "CREATE TABLE forbidden_ddl_test (id SERIAL PRIMARY KEY);"
                )
        finally:
            await conn.close()

    @pytest.mark.asyncio()
    async def test_app_user_cannot_alter_table(self) -> None:
        """stocklens_app must raise InsufficientPrivilegeError on ALTER TABLE."""
        conn = await asyncpg.connect(dsn=_dsn())
        try:
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await conn.execute(
                    "ALTER TABLE analysis_runs ADD COLUMN forbidden_col TEXT;"
                )
        finally:
            await conn.close()

    @pytest.mark.asyncio()
    async def test_app_user_has_crud_on_analysis_runs(self) -> None:
        """stocklens_app must have SELECT, INSERT, UPDATE, DELETE on analysis_runs."""
        conn = await asyncpg.connect(dsn=_dsn())
        try:
            for priv in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                row = await conn.fetchrow(
                    "SELECT has_table_privilege($1, 'analysis_runs', $2) AS ok;",
                    "stocklens_app",
                    priv,
                )
                assert row["ok"] is True, (
                    f"stocklens_app is missing {priv} on analysis_runs"
                )
        finally:
            await conn.close()

    @pytest.mark.asyncio()
    async def test_app_user_has_crud_on_pipeline_steps(self) -> None:
        """stocklens_app must have SELECT, INSERT, UPDATE, DELETE on pipeline_steps."""
        conn = await asyncpg.connect(dsn=_dsn())
        try:
            for priv in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                row = await conn.fetchrow(
                    "SELECT has_table_privilege($1, 'pipeline_steps', $2) AS ok;",
                    "stocklens_app",
                    priv,
                )
                assert row["ok"] is True, (
                    f"stocklens_app is missing {priv} on pipeline_steps"
                )
        finally:
            await conn.close()

    @pytest.mark.asyncio()
    async def test_app_user_has_crud_on_system_metrics_hourly(self) -> None:
        """stocklens_app must have SELECT, INSERT, UPDATE, DELETE on system_metrics_hourly."""
        conn = await asyncpg.connect(dsn=_dsn())
        try:
            for priv in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                row = await conn.fetchrow(
                    "SELECT has_table_privilege($1, 'system_metrics_hourly', $2) AS ok;",
                    "stocklens_app",
                    priv,
                )
                assert row["ok"] is True, (
                    f"stocklens_app is missing {priv} on system_metrics_hourly"
                )
        finally:
            await conn.close()

    @pytest.mark.asyncio()
    async def test_app_user_has_crud_on_ticker_resolution_cache(self) -> None:
        """stocklens_app must have SELECT, INSERT, UPDATE, DELETE on ticker_resolution_cache."""
        conn = await asyncpg.connect(dsn=_dsn())
        try:
            for priv in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                row = await conn.fetchrow(
                    "SELECT has_table_privilege($1, 'ticker_resolution_cache', $2) AS ok;",
                    "stocklens_app",
                    priv,
                )
                assert row["ok"] is True, (
                    f"stocklens_app is missing {priv} on ticker_resolution_cache"
                )
        finally:
            await conn.close()

    @pytest.mark.asyncio()
    async def test_rate_limit_log_is_append_only(self) -> None:
        """stocklens_app must have SELECT + INSERT on rate_limit_log, but NOT UPDATE or DELETE."""
        conn = await asyncpg.connect(dsn=_dsn())
        try:
            # Allowed privileges
            for priv in ("SELECT", "INSERT"):
                row = await conn.fetchrow(
                    "SELECT has_table_privilege($1, 'rate_limit_log', $2) AS ok;",
                    "stocklens_app",
                    priv,
                )
                assert row["ok"] is True, (
                    f"stocklens_app is missing {priv} on rate_limit_log"
                )

            # Denied privileges
            for priv in ("UPDATE", "DELETE"):
                row = await conn.fetchrow(
                    "SELECT has_table_privilege($1, 'rate_limit_log', $2) AS ok;",
                    "stocklens_app",
                    priv,
                )
                assert row["ok"] is False, (
                    f"stocklens_app must NOT have {priv} on rate_limit_log"
                )
        finally:
            await conn.close()

    @pytest.mark.asyncio()
    async def test_app_user_has_sequence_usage(self) -> None:
        """stocklens_app must have USAGE on sequences (required for autoincrement INSERTs)."""
        conn = await asyncpg.connect(dsn=_dsn())
        try:
            # Check one representative sequence — analysis_runs_id_seq
            row = await conn.fetchrow(
                "SELECT has_sequence_privilege($1, 'analysis_runs_id_seq', 'USAGE') AS ok;",
                "stocklens_app",
            )
            assert row["ok"] is True, (
                "stocklens_app is missing USAGE on analysis_runs_id_seq"
            )
        finally:
            await conn.close()

    @pytest.mark.asyncio()
    async def test_schema_create_is_revoked(self) -> None:
        """REVOKE CREATE ON SCHEMA public must deny schema-level DDL."""
        conn = await asyncpg.connect(dsn=_dsn())
        try:
            row = await conn.fetchrow(
                "SELECT has_schema_privilege($1, 'public', 'CREATE') AS ok;",
                "stocklens_app",
            )
            assert row["ok"] is False, (
                "stocklens_app must NOT have CREATE privilege on schema public"
            )
        finally:
            await conn.close()
