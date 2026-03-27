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
from app.jobs.cleanup import run_cleanup_job
from app.jobs.metrics_aggregator import run_metrics_aggregation_job
from app.pipeline.orchestrator import PipelineOrchestrator
from app.pipeline.steps import build_step_registry

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

    # ── Providers and repositories ─────────────────────────────────────────
    market_data_provider = YFinanceMarketDataProvider(
        redis=redis_client, settings=settings
    )
    news_feed_provider = RSSNewsFeedProvider(redis=redis_client, settings=settings)
    ticker_cache_repo = TickerCacheRepository(pool=db_pool, redis=redis_client)
    event_bus = RedisEventBus(redis=redis_client)
    report_repository = ReportRepository(pool=db_pool)
    prompt_loader = PromptLoader(template_dir="app/prompts")

    # ── Store on app.state before building step registry ──────────────────
    app.state.db_pool = db_pool
    app.state.redis = redis_client
    app.state.llm_semaphore = llm_semaphore
    app.state.market_data_provider = market_data_provider
    app.state.news_feed_provider = news_feed_provider
    app.state.ticker_cache_repo = ticker_cache_repo
    app.state.event_bus = event_bus
    app.state.report_repository = report_repository
    app.state.prompt_loader = prompt_loader

    # ── Build the full 9-step pipeline ────────────────────────────────────
    steps = build_step_registry(app.state)

    orchestrator = PipelineOrchestrator(
        steps=steps,
        event_bus=event_bus,
        report_repository=report_repository,
        llm_semaphore=llm_semaphore,
    )

    app.state.orchestrator = orchestrator

    # ── Launch background jobs ─────────────────────────────────────────────
    cleanup_task: asyncio.Task[None] = asyncio.create_task(
        run_cleanup_job(db_pool),
        name="cleanup-job",
    )
    metrics_task: asyncio.Task[None] = asyncio.create_task(
        run_metrics_aggregation_job(db_pool),
        name="metrics-aggregation-job",
    )

    log.info(
        "application_startup",
        version=settings.app_version,
        environment=settings.environment,
        log_level=settings.log_level,
        pipeline_steps=len(steps),
    )

    yield

    log.info("application_shutdown", version=settings.app_version)

    # ── Cancel background jobs cleanly ────────────────────────────────────
    cleanup_task.cancel()
    metrics_task.cancel()
    await asyncio.gather(cleanup_task, metrics_task, return_exceptions=True)

    await redis_client.aclose()  # type: ignore[attr-defined]
    await db_pool.close()
