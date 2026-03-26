from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import asyncpg
import structlog
from fastapi import FastAPI
from redis.asyncio import Redis

from app.config import get_settings

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

    app.state.db_pool = db_pool
    app.state.redis = redis_client
    app.state.llm_semaphore = llm_semaphore

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
