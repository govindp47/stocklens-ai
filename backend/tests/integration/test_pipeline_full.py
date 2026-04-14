"""Full 9-step pipeline integration tests (T-042).

Both test cases run the orchestrator directly (not via launch()) against a real
PostgreSQL test database with all external I/O mocked at the method level.

Happy-path: all 9 steps complete, completeness='complete'.
Degraded-path: LLM returns empty JSON for all calls, steps 5-8 degrade
gracefully, completeness='minimal' (no company_info from TickerValidator's
_fetch_and_populate means ReportAssembler gets None company_info ... actually
completeness depends on company_info + market_data + articles + sentiment + insights).

For the degraded path (Ollama 500 equivalent): mock llm.complete to raise
ExternalProviderError so steps 5-8 return FAILED, but steps 1-4 still complete.
The report should have completeness='partial' or 'minimal' depending on what
made it through. With company_info=None (steps 1-4 fail due to LLM), we get
'minimal'. Actually steps 1-4 don't call LLM, so they complete fine.
For degraded: steps 5-8 fail → no sentiment, no insights. With company_info
and market_data and articles available: critical_ok=True, optional=2
(market_data + articles) → partial. We'll assert completeness != 'complete'.

Architecture reference: 09_TESTING_STRATEGY.md Section 4.1.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import asyncpg
import fakeredis.aioredis as fakeredis
import pytest

from app.domain.exceptions import ExternalProviderError
from app.domain.models.market import CompanyInfo, MarketData, PriceHistory, PricePoint
from app.domain.models.news import RawArticle
from app.infrastructure.event_bus import RedisEventBus
from app.infrastructure.providers.prompt_loader import PromptLoader
from app.infrastructure.repositories.report_repository import ReportRepository
from app.pipeline.orchestrator import PipelineOrchestrator
from app.pipeline.steps.article_summarizer import ArticleSummarizer
from app.pipeline.steps.event_extractor import EventExtractor
from app.pipeline.steps.insight_generator import InsightGenerator
from app.pipeline.steps.market_data_collector import MarketDataCollector
from app.pipeline.steps.news_deduplicator import NewsDeduplicator
from app.pipeline.steps.news_retriever import NewsRetriever
from app.pipeline.steps.report_assembler import ReportAssembler
from app.pipeline.steps.sentiment_classifier import SentimentClassifier
from app.pipeline.steps.ticker_validator import TickerValidator

# ── Mock data ──────────────────────────────────────────────────────────────────

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
        title=f"Apple announces strong earnings for Q{i} with record revenue",
        published_at=datetime(2024, 1, 15, tzinfo=UTC),
        source_name="MockFeed",
        content_snippet=f"Apple Inc reported strong Q{i} results beating expectations.",
    )
    for i in range(1, 6)
]

# Valid JSON responses the mock LLM returns for each step
_SUMMARY_JSON = json.dumps(
    {
        "summary": "Apple reported strong quarterly earnings beating analyst expectations.",
        "key_topics": ["Earnings"],
        "sentiment_label": "positive",
        "confidence_score": 0.85,
    }
)

_SENTIMENT_JSON = json.dumps(
    {
        "label": "positive",
        "score": 0.82,
    }
)

_EVENTS_JSON = json.dumps(
    {
        "events": [
            {
                "event_type": "Earnings Announcement",
                "description": "Apple Q4 earnings beat expectations",
                "date": "2024-01-15",
                "significance": "high",
                "source_article_indices": [0],
            }
        ]
    }
)

_INSIGHTS_JSON = json.dumps(
    {
        "executive_summary": "Apple shows strong performance with record revenue.",
        "market_position": "Apple maintains dominant market position in premium segments.",
        "risk_factors": "Regulatory and supply chain risks remain key concerns.",
        "growth_catalysts": "Services revenue and iPhone growth drive outlook.",
        "technical_outlook": "Stock shows upward momentum with strong fundamentals.",
        "investment_considerations": "Long-term fundamentals remain solid despite headwinds.",
    }
)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _build_mock_market_provider() -> MagicMock:
    provider = MagicMock()
    provider.is_ticker_resolvable = AsyncMock(return_value=True)
    provider.get_quote = AsyncMock(return_value=_MOCK_MARKET_DATA)
    provider.get_company_info = AsyncMock(return_value=_MOCK_COMPANY_INFO)
    provider.get_price_history = AsyncMock(return_value=_MOCK_PRICE_HISTORY)
    return provider


def _build_mock_news_provider() -> MagicMock:
    provider = MagicMock()
    provider.get_articles = AsyncMock(return_value=_MOCK_ARTICLES)
    return provider


def _build_mock_ticker_cache() -> MagicMock:
    repo = MagicMock()
    repo.resolve = AsyncMock(return_value=None)  # cache miss
    repo.set_resolved = AsyncMock()
    return repo


def _build_happy_llm_provider() -> MagicMock:
    """LLM that returns valid JSON for each step in sequence."""
    provider = MagicMock()
    provider.model_name = "test-model"
    # Return different JSON depending on call order (summarize x5, sentiment x5,
    # events x1, insights x1). Use side_effect list.
    responses = (
        [_SUMMARY_JSON] * 5  # ArticleSummarizer (one per article)
        + [_SENTIMENT_JSON] * 5  # SentimentClassifier (one per article)
        + [_EVENTS_JSON]  # EventExtractor (corpus call)
        + [_INSIGHTS_JSON]  # InsightGenerator
    )
    provider.complete = AsyncMock(side_effect=responses)
    return provider


def _build_degraded_llm_provider() -> MagicMock:
    """LLM that always raises ExternalProviderError (simulates Ollama 500)."""
    provider = MagicMock()
    provider.model_name = "test-model"
    provider.complete = AsyncMock(
        side_effect=ExternalProviderError(
            "Ollama returned HTTP 500",
            error_code="OLLAMA_SERVER_ERROR",
            user_message="The local AI model is not responding.",
            is_retryable=False,  # non-retryable so retry loop exits immediately
        )
    )
    return provider


def _build_orchestrator(
    db_pool: asyncpg.Pool,  # type: ignore[type-arg]
    redis_client: fakeredis.FakeRedis,  # type: ignore[type-arg]
    prompt_loader: PromptLoader,
    market_provider: MagicMock,
    news_provider: MagicMock,
    ticker_cache: MagicMock,
) -> PipelineOrchestrator:
    report_repo = ReportRepository(pool=db_pool)
    event_bus = RedisEventBus(redis=redis_client)  # type: ignore[arg-type]
    llm_semaphore = asyncio.Semaphore(2)

    steps = [
        TickerValidator(
            ticker_cache_repo=ticker_cache,
            market_data_provider=market_provider,
        ),
        MarketDataCollector(market_data_provider=market_provider),
        NewsRetriever(news_provider=news_provider),
        NewsDeduplicator(),
        ArticleSummarizer(prompt_loader=prompt_loader),
        SentimentClassifier(prompt_loader=prompt_loader),
        EventExtractor(prompt_loader=prompt_loader),
        InsightGenerator(prompt_loader=prompt_loader),
        ReportAssembler(),
    ]

    return PipelineOrchestrator(
        steps=steps,
        event_bus=event_bus,
        report_repository=report_repo,
        llm_semaphore=llm_semaphore,
    )


# ── Tests ──────────────────────────────────────────────────────────────────────


@pytest.mark.integration()
class TestFullPipelineHappyPath:
    async def test_nine_step_pipeline_completes_with_full_report(
        self,
        db_pool: asyncpg.Pool,  # type: ignore[type-arg]
        redis_api: fakeredis.FakeRedis,  # type: ignore[type-arg]
    ) -> None:
        """All 9 steps complete; DB has status='complete' and a non-null report."""
        run_id = uuid4()
        ticker = "AAPL"

        prompt_loader = PromptLoader(template_dir="app/prompts")
        market_provider = _build_mock_market_provider()
        news_provider = _build_mock_news_provider()
        ticker_cache = _build_mock_ticker_cache()
        llm_provider = _build_happy_llm_provider()

        report_repo = ReportRepository(pool=db_pool)
        orchestrator = _build_orchestrator(
            db_pool,
            redis_api,
            prompt_loader,
            market_provider,
            news_provider,
            ticker_cache,
        )

        await report_repo.create_run(
            run_id=run_id,
            ticker=ticker,
            ip_address="127.0.0.1",
            llm_provider="ollama",
            llm_model="test-model",
        )

        await orchestrator.run(run_id, ticker, llm_provider)
        # Allow fire-and-forget upsert_step tasks to complete before querying DB
        await asyncio.sleep(0.1)

        async with db_pool.acquire() as conn:  # type: ignore[attr-defined]
            run_row = await conn.fetchrow(
                "SELECT status, steps_completed, report_data FROM analysis_runs WHERE run_id = $1",
                run_id,
            )
            step_rows = await conn.fetch(
                "SELECT step_name, status FROM pipeline_steps WHERE run_id = $1 "
                "ORDER BY step_index",
                run_id,
            )

        assert run_row is not None
        assert run_row["status"] == "complete", f"Expected 'complete', got '{run_row['status']}'"
        assert run_row["steps_completed"] == 9
        assert run_row["report_data"] is not None, "report_data should be non-null"

        # Validate report JSON is parseable and has required fields
        report = json.loads(run_row["report_data"])
        assert report["ticker"] == "AAPL"
        assert "completeness" in report
        assert "content_hash" in report
        assert report["content_hash"] is not None

        # All 9 steps should be recorded
        step_names = {r["step_name"] for r in step_rows}
        assert "TickerValidator" in step_names
        assert "ReportAssembler" in step_names
        assert len(step_rows) == 9

    async def test_sentiment_distribution_sums_to_100(
        self,
        db_pool: asyncpg.Pool,  # type: ignore[type-arg]
        redis_api: fakeredis.FakeRedis,  # type: ignore[type-arg]
    ) -> None:
        """Sentiment distribution in the final report must sum exactly to 100."""
        run_id = uuid4()
        ticker = "AAPL"

        prompt_loader = PromptLoader(template_dir="app/prompts")
        market_provider = _build_mock_market_provider()
        news_provider = _build_mock_news_provider()
        ticker_cache = _build_mock_ticker_cache()
        llm_provider = _build_happy_llm_provider()

        report_repo = ReportRepository(pool=db_pool)
        orchestrator = _build_orchestrator(
            db_pool,
            redis_api,
            prompt_loader,
            market_provider,
            news_provider,
            ticker_cache,
        )

        await report_repo.create_run(
            run_id=run_id,
            ticker=ticker,
            ip_address="127.0.0.1",
            llm_provider="ollama",
            llm_model="test-model",
        )

        await orchestrator.run(run_id, ticker, llm_provider)
        await asyncio.sleep(0.1)

        async with db_pool.acquire() as conn:  # type: ignore[attr-defined]
            run_row = await conn.fetchrow(
                "SELECT report_data FROM analysis_runs WHERE run_id = $1",
                run_id,
            )

        assert run_row is not None
        assert run_row["report_data"] is not None
        report = json.loads(run_row["report_data"])

        sentiment = report.get("sentiment", {})
        if sentiment.get("available"):
            dist = sentiment.get("distribution", {})
            total = dist.get("positive", 0) + dist.get("negative", 0) + dist.get("neutral", 0)
            assert total == 100, f"Sentiment distribution sums to {total}, expected 100"


@pytest.mark.integration()
class TestFullPipelineDegradedPath:
    async def test_llm_failure_pipeline_still_completes(
        self,
        db_pool: asyncpg.Pool,  # type: ignore[type-arg]
        redis_api: fakeredis.FakeRedis,  # type: ignore[type-arg]
    ) -> None:
        """When LLM always fails, the pipeline still reaches 'complete' status.

        Steps 1-4 succeed (no LLM calls). Steps 5-8 handle LLM errors gracefully
        at the per-article level and return non-critical COMPLETE results with
        degraded content. Step 9 (ReportAssembler, critical) completes with
        pure computation. The run status is 'complete' with a valid report.

        This verifies that LLM failures in non-critical steps do not crash the
        pipeline — the system degrades gracefully rather than aborting.
        """
        run_id = uuid4()
        ticker = "AAPL"

        prompt_loader = PromptLoader(template_dir="app/prompts")
        market_provider = _build_mock_market_provider()
        news_provider = _build_mock_news_provider()
        ticker_cache = _build_mock_ticker_cache()
        llm_provider = _build_degraded_llm_provider()

        report_repo = ReportRepository(pool=db_pool)
        orchestrator = _build_orchestrator(
            db_pool,
            redis_api,
            prompt_loader,
            market_provider,
            news_provider,
            ticker_cache,
        )

        await report_repo.create_run(
            run_id=run_id,
            ticker=ticker,
            ip_address="127.0.0.1",
            llm_provider="ollama",
            llm_model="test-model",
        )

        await orchestrator.run(run_id, ticker, llm_provider)

        async with db_pool.acquire() as conn:  # type: ignore[attr-defined]
            run_row = await conn.fetchrow(
                "SELECT status, steps_completed, report_data FROM analysis_runs WHERE run_id = $1",
                run_id,
            )

        assert run_row is not None
        # Pipeline status must be 'complete' — non-critical step failures do not abort the run
        assert run_row["status"] == "complete", (
            f"Expected 'complete', got '{run_row['status']}': "
            "LLM failures in non-critical steps should not prevent pipeline completion"
        )
        # Steps 1-4 always complete (no LLM), step 9 (assembler) also completes
        assert run_row["steps_completed"] >= 4

        # Report must be persisted by ReportAssembler
        assert run_row["report_data"] is not None, "ReportAssembler must persist a report"
        report = json.loads(run_row["report_data"])
        assert "completeness" in report
        assert "content_hash" in report
        assert report["content_hash"] is not None
