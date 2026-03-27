"""Integration test fixtures — provides a test HTTP client with overridden app state.

The ``client`` fixture creates a minimal FastAPI app (no lifespan) with:
  - Real asyncpg pool (test DB at 127.0.0.1:5433)
  - In-process fakeredis with decode_responses=True (mirrors production settings)
  - A MagicMock orchestrator (avoids launching real pipeline in API tests)
  - An asyncio.Semaphore for llm_semaphore

This approach bypasses the production lifespan so tests are not affected by
missing environment variables (Ollama URL, yfinance, etc.).

Note: the ``redis`` fixture here overrides the global conftest fixture for
integration tests, using ``decode_responses=True`` to match the production
Redis client configuration.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import fakeredis as _fakeredis
import fakeredis.aioredis as fakeredis
import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

from app.api.routers import analyze, health, stream


@pytest.fixture
async def redis_api() -> fakeredis.FakeRedis:  # type: ignore[type-arg, misc]
    """In-process fakeredis with ``decode_responses=True`` for API-layer tests.

    Matches the production Redis client configuration so that lrange / Pub/Sub
    message payloads arrive as strings (not bytes) in the stream router.

    Used by the ``client`` fixture and by stream/pipeline tests that publish
    events and need string payloads.  The global ``redis`` fixture (which uses
    ``decode_responses=False``) is kept unchanged so repository tests are
    unaffected.
    """
    server = _fakeredis.FakeServer()
    client: fakeredis.FakeRedis = fakeredis.FakeRedis(  # type: ignore[type-arg]
        server=server, decode_responses=True
    )
    yield client  # type: ignore[misc]
    await client.flushall()
    await client.aclose()


@pytest.fixture
async def client(
    db_pool: object,
    redis_api: fakeredis.FakeRedis,  # type: ignore[type-arg]
) -> AsyncClient:  # type: ignore[misc]
    """Async HTTP test client backed by a minimal FastAPI app (no lifespan).

    Uses the ``redis_api`` fixture (decode_responses=True) to match production.
    The orchestrator is a MagicMock whose ``launch`` method returns the run_id
    unchanged — no background pipeline tasks are spawned during API tests.
    """
    test_app = FastAPI(title="StockLens Test")

    # ── Wire test state ────────────────────────────────────────────────────
    test_app.state.db_pool = db_pool
    test_app.state.redis = redis_api
    test_app.state.llm_semaphore = asyncio.Semaphore(2)

    # Mock orchestrator — launch() is a no-op that returns the run_id so the
    # pipeline is never started during API-layer tests.
    mock_orchestrator = MagicMock()
    mock_orchestrator.launch = lambda run_id, ticker, llm_provider, **_kw: run_id
    test_app.state.orchestrator = mock_orchestrator

    # ── Register routers ───────────────────────────────────────────────────
    test_app.include_router(health.router)
    test_app.include_router(analyze.router, prefix="/api/v1")
    test_app.include_router(stream.router, prefix="/api/v1")

    transport = ASGITransport(app=test_app)  # type: ignore[arg-type]
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as ac:
        yield ac  # type: ignore[misc]
