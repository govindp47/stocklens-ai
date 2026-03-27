"""Pipeline integration test — Steps 1–4 (T-030).

Runs the full 4-step pipeline (TickerValidator → MarketDataCollector →
NewsRetriever → NewsDeduplicator) against a real PostgreSQL test database.

External provider calls (yfinance / feedparser) are mocked at the method level
using ``unittest.mock.AsyncMock`` so no HTTP traffic leaves the test process.

Acceptance criteria (from T-030):
  - ``analysis_runs`` row has ``steps_completed=4`` and ``status='complete'``
    after the mock pipeline completes.
  - All four ``pipeline_steps`` records exist with ``status='complete'``.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import asyncpg
import fakeredis.aioredis as fakeredis
import pytest

from app.domain.models.market import CompanyInfo, MarketData, PriceHistory, PricePoint
from app.domain.models.news import RawArticle
from app.infrastructure.event_bus import RedisEventBus
from app.infrastructure.repositories.report_repository import ReportRepository
from app.infrastructure.repositories.ticker_cache_repository import TickerCacheRepository
from app.pipeline.orchestrator import PipelineOrchestrator
from app.pipeline.steps.market_data_collector import MarketDataCollector
from app.pipeline.steps.news_deduplicator import NewsDeduplicator
from app.pipeline.steps.news_retriever import NewsRetriever
from app.pipeline.steps.ticker_validator import TickerValidator


# ── Mock data ─────────────────────────────────────────────────────────────────

_MOCK_COMPANY_INFO = CompanyInfo(
    ticker="AAPL",
    name="Apple Inc.",
    exchange="NASDAQ",
    sector="Technology",
    currency="USD",
    country="US",
)

_MOCK_MARKET_DATA = MarketData(
    available=True,
    price=175.50,
    change_pct=1.2,
    change_abs=2.10,
    volume=55_000_000.0,
    market_cap=2_700_000_000_000.0,
    pe_ratio=28.5,
    currency="USD",
)

_MOCK_PRICE_HISTORY = PriceHistory(
    available=True,
    datapoints=[
        PricePoint(
            date=f"2024-01-{i:02d}",
            open=170.0 + i,
            high=172.0 + i,
            low=169.0 + i,
            close=171.0 + i,
            volume=50_000_000.0,
        )
        for i in range(1, 21)
    ],
    trend_direction="upward",
    volatility_flag=False,
)

_MOCK_ARTICLES = [
    RawArticle(
        article_id=f"art{i:010d}",
        url=f"https://news.example.com/aapl/{i}",
        title=f"Apple news article number {i} about earnings and growth",
        published_at=datetime(2024, 1, 15, tzinfo=UTC),
        source_name="MockFeed",
    )
    for i in range(1, 6)
]


# ── Helpers ───────────────────────────────────────────────────────────────────


def _build_mock_market_data_provider() -> MagicMock:
    """Return a fully mocked YFinanceMarketDataProvider."""
    provider = MagicMock()
    provider.is_ticker_resolvable = AsyncMock(return_value=True)
    provider.get_quote = AsyncMock(return_value=_MOCK_MARKET_DATA)
    provider.get_company_info = AsyncMock(return_value=_MOCK_COMPANY_INFO)
    provider.get_price_history = AsyncMock(return_value=_MOCK_PRICE_HISTORY)
    return provider


def _build_mock_news_provider() -> MagicMock:
    """Return a fully mocked RSSNewsFeedProvider."""
    provider = MagicMock()
    provider.get_articles = AsyncMock(return_value=_MOCK_ARTICLES)
    return provider


def _build_mock_ticker_cache_repo() -> MagicMock:
    """Return a mocked TickerCacheRepository that always reports cache miss."""
    repo = MagicMock()
    repo.resolve = AsyncMock(return_value=None)  # cache miss → hit provider
    repo.set_resolved = AsyncMock()
    return repo


def _build_mock_llm_provider() -> MagicMock:
    """Return a MagicMock LLM provider (Steps 1–4 don't call the LLM)."""
    provider = MagicMock()
    provider.model_name = "ollama"
    provider.complete = AsyncMock(return_value="{}")
    return provider


@pytest.mark.integration
class TestPipelineSteps1To4:

    async def test_four_step_pipeline_completes(
        self,
        db_pool: asyncpg.Pool,  # type: ignore[type-arg]
        redis_api: fakeredis.FakeRedis,  # type: ignore[type-arg]
    ) -> None:
        """Full 4-step pipeline runs to completion; DB reflects steps_completed=4."""
        run_id = uuid4()
        ticker = "AAPL"

        # ── Arrange ───────────────────────────────────────────────────────────
        mock_market_provider = _build_mock_market_data_provider()
        mock_news_provider = _build_mock_news_provider()
        mock_ticker_cache = _build_mock_ticker_cache_repo()
        mock_llm = _build_mock_llm_provider()

        report_repo = ReportRepository(pool=db_pool)
        event_bus = RedisEventBus(redis=redis_api)  # type: ignore[arg-type]
        llm_semaphore = asyncio.Semaphore(2)

        steps = [
            TickerValidator(
                ticker_cache_repo=mock_ticker_cache,
                market_data_provider=mock_market_provider,
            ),
            MarketDataCollector(market_data_provider=mock_market_provider),
            NewsRetriever(news_provider=mock_news_provider),
            NewsDeduplicator(),
        ]

        orchestrator = PipelineOrchestrator(
            steps=steps,
            event_bus=event_bus,
            report_repository=report_repo,
            llm_semaphore=llm_semaphore,
        )

        # Create the run row in accepted state before launching.
        await report_repo.create_run(
            run_id=run_id,
            ticker=ticker,
            ip_address="127.0.0.1",
            llm_provider="ollama",
            llm_model=None,
        )

        # ── Act ───────────────────────────────────────────────────────────────
        # Run the orchestrator synchronously (not via launch to avoid asyncio
        # task scheduling complexity in tests).
        await orchestrator.run(run_id, ticker, mock_llm)

        # ── Assert: DB state ──────────────────────────────────────────────────
        async with db_pool.acquire() as conn:  # type: ignore[attr-defined]
            run_row = await conn.fetchrow(
                "SELECT status, steps_completed FROM analysis_runs WHERE run_id = $1",
                run_id,
            )
            step_rows = await conn.fetch(
                "SELECT step_name, status FROM pipeline_steps WHERE run_id = $1 ORDER BY step_index",
                run_id,
            )

        assert run_row is not None, "analysis_runs row not found"
        assert run_row["status"] == "complete", (
            f"Expected status='complete', got '{run_row['status']}'"
        )
        assert run_row["steps_completed"] == 4, (
            f"Expected steps_completed=4, got {run_row['steps_completed']}"
        )

        step_names = [r["step_name"] for r in step_rows]
        assert "TickerValidator" in step_names
        assert "MarketDataCollector" in step_names
        assert "NewsRetriever" in step_names
        assert "NewsDeduplicator" in step_names

        for row in step_rows:
            assert row["status"] == "complete", (
                f"Step '{row['step_name']}' has status '{row['status']}', expected 'complete'"
            )

    async def test_ticker_validator_critical_failure_halts_pipeline(
        self,
        db_pool: asyncpg.Pool,  # type: ignore[type-arg]
        redis_api: fakeredis.FakeRedis,  # type: ignore[type-arg]
    ) -> None:
        """When TickerValidator fails, the pipeline halts and the run is marked failed."""
        from app.domain.exceptions import TickerNotResolvableError

        run_id = uuid4()
        ticker = "ZZZZ"

        # Make the cache miss, then the provider returns unresolvable.
        mock_market_provider = _build_mock_market_data_provider()
        mock_market_provider.is_ticker_resolvable = AsyncMock(return_value=False)
        mock_ticker_cache = _build_mock_ticker_cache_repo()

        report_repo = ReportRepository(pool=db_pool)
        event_bus = RedisEventBus(redis=redis_api)  # type: ignore[arg-type]
        llm_semaphore = asyncio.Semaphore(2)

        steps = [
            TickerValidator(
                ticker_cache_repo=mock_ticker_cache,
                market_data_provider=mock_market_provider,
            ),
            MarketDataCollector(market_data_provider=mock_market_provider),
            NewsRetriever(news_provider=_build_mock_news_provider()),
            NewsDeduplicator(),
        ]

        orchestrator = PipelineOrchestrator(
            steps=steps,
            event_bus=event_bus,
            report_repository=report_repo,
            llm_semaphore=llm_semaphore,
        )

        await report_repo.create_run(
            run_id=run_id,
            ticker=ticker,
            ip_address="127.0.0.1",
            llm_provider="ollama",
            llm_model=None,
        )

        await orchestrator.run(run_id, ticker, _build_mock_llm_provider())

        async with db_pool.acquire() as conn:  # type: ignore[attr-defined]
            row = await conn.fetchrow(
                "SELECT status, steps_completed FROM analysis_runs WHERE run_id = $1",
                run_id,
            )

        assert row is not None
        assert row["status"] == "failed"
        assert row["steps_completed"] == 0

    async def test_sse_events_published_in_order(
        self,
        db_pool: asyncpg.Pool,  # type: ignore[type-arg]
        redis_api: fakeredis.FakeRedis,  # type: ignore[type-arg]
    ) -> None:
        """Step events in the Redis list are in ascending step_index order."""
        import json as _json

        run_id = uuid4()
        ticker = "TSLA"

        mock_market_provider = _build_mock_market_data_provider()
        mock_news_provider = _build_mock_news_provider()
        mock_ticker_cache = _build_mock_ticker_cache_repo()

        report_repo = ReportRepository(pool=db_pool)
        event_bus = RedisEventBus(redis=redis_api)  # type: ignore[arg-type]
        llm_semaphore = asyncio.Semaphore(2)

        steps = [
            TickerValidator(
                ticker_cache_repo=mock_ticker_cache,
                market_data_provider=mock_market_provider,
            ),
            MarketDataCollector(market_data_provider=mock_market_provider),
            NewsRetriever(news_provider=mock_news_provider),
            NewsDeduplicator(),
        ]

        orchestrator = PipelineOrchestrator(
            steps=steps,
            event_bus=event_bus,
            report_repository=report_repo,
            llm_semaphore=llm_semaphore,
        )

        await report_repo.create_run(
            run_id=run_id,
            ticker=ticker,
            ip_address="127.0.0.1",
            llm_provider="ollama",
            llm_model=None,
        )
        await orchestrator.run(run_id, ticker, _build_mock_llm_provider())

        # Read the Redis event list.
        list_key = f"pipeline:list:{run_id}"
        raw_events: list[str] = await redis_api.lrange(list_key, 0, -1)
        events = [_json.loads(r) for r in raw_events]

        step_update_events = [e for e in events if e.get("type") == "step_update"]
        complete_events = [e for e in step_update_events if e.get("status") == "complete"]
        indices = [e["step_index"] for e in complete_events]

        assert indices == sorted(indices), (
            f"Step events not in ascending order: {indices}"
        )
        assert len(indices) == 4, f"Expected 4 complete step events, got {len(indices)}"
        assert indices[0] == 1, "First step index must be 1 (TickerValidator)"
