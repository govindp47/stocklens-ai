"""Shared pytest fixtures for StockLens AI backend tests.

db_dsn  — session-scoped SYNC fixture returning the test database DSN string.
db_pool — function-scoped async fixture; creates one asyncpg pool per test.
          Function scope is required: pytest-asyncio 0.23.x creates a separate
          event loop per test function, so a session-scoped pool would cross
          loop boundaries and cause 'Future attached to a different loop' errors.
redis   — function-scoped in-process fakeredis.
clean_db — autouse; truncates all tables before each integration test.
"""

from __future__ import annotations

import os

import asyncpg
import fakeredis.aioredis as fakeredis
import pytest

# ---------------------------------------------------------------------------
# DSN helper — sync, session-scoped; no asyncio involved
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def db_dsn() -> str:
    """Return the test database DSN string.

    Function-scoped async fixtures use this to create per-test pools.
    """
    return os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql://stocklens:test@127.0.0.1:5433/stocklens_test",
    )


# ---------------------------------------------------------------------------
# Database pool — function-scoped to match pytest-asyncio's per-test loop
# ---------------------------------------------------------------------------


@pytest.fixture()
async def db_pool(db_dsn: str) -> asyncpg.Pool:  # type: ignore[return, type-arg]
    """asyncpg connection pool for integration tests.

    Created fresh for each test to stay within the function-scoped event loop
    that pytest-asyncio 0.23.x creates per test function.
    """
    pool: asyncpg.Pool = await asyncpg.create_pool(dsn=db_dsn, min_size=1, max_size=5)  # type: ignore[type-arg]
    yield pool  # type: ignore[misc]
    await pool.close()


# ---------------------------------------------------------------------------
# Redis (unit + integration tests — in-process fake, no external connection)
# ---------------------------------------------------------------------------


@pytest.fixture()
async def redis() -> fakeredis.FakeRedis:  # type: ignore[type-arg]
    """In-process fake Redis; safe for tests with no external dependency."""
    client: fakeredis.FakeRedis = fakeredis.FakeRedis(decode_responses=False)  # type: ignore[type-arg]
    yield client
    await client.flushall()
    await client.aclose()


# ---------------------------------------------------------------------------
# Clean database — truncate all tables before each integration test
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
async def _clean_db(db_dsn: str, request: pytest.FixtureRequest) -> None:
    """Truncate all application tables before each integration test.

    Creates its own short-lived connection so it does not compete with the
    test's db_pool fixture for connections. Only runs for tests marked with
    @pytest.mark.integration.
    """
    if "integration" not in request.keywords:
        return
    conn: asyncpg.Connection = await asyncpg.connect(dsn=db_dsn)  # type: ignore[type-arg]
    try:
        await conn.execute(
            """
            TRUNCATE
                analysis_runs,
                pipeline_steps,
                system_metrics_hourly,
                ticker_resolution_cache,
                rate_limit_log
            RESTART IDENTITY CASCADE
            """
        )
    finally:
        await conn.close()
