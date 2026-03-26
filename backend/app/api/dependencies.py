from __future__ import annotations

import asyncio

import asyncpg
from fastapi import Request
from redis.asyncio import Redis

from app.config import Settings, get_settings


def get_db_pool(request: Request) -> asyncpg.Pool:
    pool: asyncpg.Pool = request.app.state.db_pool
    return pool


def get_redis(request: Request) -> Redis:  # type: ignore[type-arg]
    client: Redis[str] = request.app.state.redis
    return client


def get_llm_semaphore(request: Request) -> asyncio.Semaphore:
    semaphore: asyncio.Semaphore = request.app.state.llm_semaphore
    return semaphore


# Re-exported so callers can use `from app.api.dependencies import get_settings`
__all__ = ["get_db_pool", "get_redis", "get_llm_semaphore", "get_settings", "Settings"]
