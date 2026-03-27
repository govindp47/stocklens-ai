from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import asyncpg
import structlog
from fastapi import FastAPI
from redis.asyncio import Redis

from app.config import get_settings
from app.infrastructure.event_bus import RedisEventBus
from app.infrastructure.providers.market_data import YFinanceMarketDataProvider
from app.infrastructure.providers.news_feed import RSSNewsFeedProvider
from app.infrastructure.providers.prompt_loader import PromptLoader
from app.infrastructure.repositories.report_repository import ReportRepository
from app.infrastructure.repositories.ticker_cache_repository import TickerCacheRepository
from app.pipeline.orchestrator import PipelineOrchestrator
from app.pipeline.steps.base import PipelineStep
from app.pipeline.steps.market_data_collector import MarketDataCollector
from app.pipeline.steps.news_deduplicator import NewsDeduplicator
from app.pipeline.steps.news_retriever import NewsRetriever
from app.pipeline.steps.ticker_validator import TickerValidator

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()

    # Strip SQLAlchemy driver prefix — asyncpg uses plain postgresql:// DSN
    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")

    db_pool: asyncpg.Pool = await asyncpg.create_pool(
        dsn=dsn,
        min_size=2,
        max_size=10,
        command_timeout=10,
    )

    redis_client: Redis[str] = Redis.from_url(
        settings.redis_url,
        max_connections=20,
        decode_responses=True,
    )

    llm_semaphore = asyncio.Semaphore(settings.max_concurrent_llm_calls)

    # ── Wire up the pipeline orchestrator ─────────────────────────────────────
    market_data_provider = YFinanceMarketDataProvider(
        redis=redis_client, settings=settings
    )
    news_feed_provider = RSSNewsFeedProvider(redis=redis_client, settings=settings)
    ticker_cache_repo = TickerCacheRepository(pool=db_pool, redis=redis_client)
    event_bus = RedisEventBus(redis=redis_client)
    report_repository = ReportRepository(pool=db_pool)

    steps: list[PipelineStep] = [
        TickerValidator(
            ticker_cache_repo=ticker_cache_repo,
            market_data_provider=market_data_provider,
        ),
        MarketDataCollector(market_data_provider=market_data_provider),
        NewsRetriever(news_provider=news_feed_provider),
        NewsDeduplicator(),
    ]

    orchestrator = PipelineOrchestrator(
        steps=steps,
        event_bus=event_bus,
        report_repository=report_repository,
        llm_semaphore=llm_semaphore,
    )

    app.state.db_pool = db_pool
    app.state.redis = redis_client
    app.state.llm_semaphore = llm_semaphore
    app.state.orchestrator = orchestrator
    app.state.prompt_loader = PromptLoader(template_dir="app/prompts")

    log.info(
        "application_startup",
        version=settings.app_version,
        environment=settings.environment,
        log_level=settings.log_level,
    )

    yield

    log.info("application_shutdown", version=settings.app_version)

    await redis_client.aclose()  # type: ignore[attr-defined]
    await db_pool.close()
