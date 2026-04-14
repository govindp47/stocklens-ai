"""TickerCacheRepository — two-level ticker resolution cache.

Cache hierarchy:
  1. Redis (hot cache, TTL = 3600 s for resolvable, 86400 s for negative)
  2. PostgreSQL ticker_resolution_cache table (TTL enforced at application layer)

resolve(ticker) semantics:
  - Returns True  → ticker is cached and resolvable.
  - Returns False → ticker is cached as non-resolvable (negative cache).
  - Returns None  → ticker is not in cache; caller must hit the external provider.

Negative caching prevents repeated yfinance lookups for delisted/unknown tickers.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
import redis.asyncio as aioredis

from app.domain.exceptions import ExternalProviderError

logger = logging.getLogger(__name__)

# Redis TTL constants (seconds)
_REDIS_TTL_RESOLVABLE: int = 3_600  # 1 hour
_REDIS_TTL_NEGATIVE: int = 86_400  # 24 hours

# PostgreSQL TTL constants (timedelta)
_PG_TTL_RESOLVABLE: timedelta = timedelta(hours=1)
_PG_TTL_NEGATIVE: timedelta = timedelta(hours=24)

# Redis key prefix
_KEY_PREFIX = "ticker_cache:"


class TickerCacheRepository:
    """Two-level (Redis + PostgreSQL) cache for ticker resolution results."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        redis: aioredis.Redis,  # type: ignore[type-arg]
    ) -> None:
        self._pool = pool
        self._redis = redis

    # ──────────────────────────────────────────────────────────────────────
    # Public interface
    # ──────────────────────────────────────────────────────────────────────

    async def resolve(self, ticker: str) -> bool | None:
        """Look up ticker in the cache.

        Returns:
            True   — ticker is known-resolvable.
            False  — ticker is known-unresolvable (negative cache).
            None   — cache miss; caller must hit the external provider.
        """
        # 1. Redis hot-cache lookup (cheapest)
        redis_result = await self._redis_get(ticker)
        if redis_result is not None:
            return redis_result

        # 2. PostgreSQL fallback (cold-start / Redis miss)
        pg_result = await self._pg_get(ticker)
        if pg_result is not None:
            # Warm Redis from the PostgreSQL record
            await self._redis_set(ticker, pg_result)
            return pg_result

        return None  # cache miss

    async def set_resolved(
        self,
        ticker: str,
        is_resolvable: bool,
        company_name: str | None = None,
        exchange: str | None = None,
        sector: str | None = None,
        industry: str | None = None,
        currency: str | None = None,
        country: str | None = None,
    ) -> None:
        """Write a resolution result to both Redis and PostgreSQL.

        Writes Redis first (fast path), then PostgreSQL (durable).
        A failure writing PostgreSQL is logged but not re-raised so the
        pipeline is not blocked by a DB write failure for cache data.
        """
        await self._redis_set(ticker, is_resolvable)
        try:
            await self._pg_upsert(
                ticker,
                is_resolvable,
                company_name=company_name,
                exchange=exchange,
                sector=sector,
                industry=industry,
                currency=currency,
                country=country,
            )
        except ExternalProviderError:
            logger.warning("Failed to persist ticker cache to PostgreSQL", extra={"ticker": ticker})

    # ──────────────────────────────────────────────────────────────────────
    # Redis helpers
    # ──────────────────────────────────────────────────────────────────────

    def _redis_key(self, ticker: str) -> str:
        return f"{_KEY_PREFIX}{ticker}"

    async def _redis_get(self, ticker: str) -> bool | None:
        try:
            value: bytes | None = await self._redis.get(self._redis_key(ticker))
            if value is None:
                return None
            return value == b"1"
        except Exception as exc:
            logger.warning("Redis get failed for ticker %s: %s", ticker, exc)
            return None  # degrade gracefully; fall through to PostgreSQL

    async def _redis_set(self, ticker: str, is_resolvable: bool) -> None:
        ttl = _REDIS_TTL_RESOLVABLE if is_resolvable else _REDIS_TTL_NEGATIVE
        try:
            await self._redis.set(self._redis_key(ticker), "1" if is_resolvable else "0", ex=ttl)
        except Exception as exc:
            logger.warning("Redis set failed for ticker %s: %s", ticker, exc)

    # ──────────────────────────────────────────────────────────────────────
    # PostgreSQL helpers
    # ──────────────────────────────────────────────────────────────────────

    async def _pg_get(self, ticker: str) -> bool | None:
        """Read from ticker_resolution_cache; respect the expires_at TTL."""
        sql = """
            SELECT is_resolvable
            FROM   ticker_resolution_cache
            WHERE  ticker     = $1
              AND  expires_at > NOW()
        """
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(sql, ticker)
            if row is None:
                return None
            return bool(row["is_resolvable"])
        except asyncpg.PostgresError as exc:
            raise ExternalProviderError(
                f"Failed to read ticker cache for {ticker}: {exc}",
                error_code="DB_TICKER_CACHE_READ_ERROR",
                user_message="Ticker cache lookup failed.",
                is_retryable=True,
            ) from exc

    async def _pg_upsert(
        self,
        ticker: str,
        is_resolvable: bool,
        **metadata: Any,
    ) -> None:
        """Write or update the ticker_resolution_cache row."""
        ttl = _PG_TTL_RESOLVABLE if is_resolvable else _PG_TTL_NEGATIVE
        expires_at = datetime.now(tz=UTC) + ttl

        sql = """
            INSERT INTO ticker_resolution_cache
                (ticker, company_name, exchange, sector, industry,
                 currency, country, is_resolvable, resolved_at, expires_at)
            VALUES
                ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), $9)
            ON CONFLICT (ticker)
            DO UPDATE SET
                company_name  = EXCLUDED.company_name,
                exchange      = EXCLUDED.exchange,
                sector        = EXCLUDED.sector,
                industry      = EXCLUDED.industry,
                currency      = EXCLUDED.currency,
                country       = EXCLUDED.country,
                is_resolvable = EXCLUDED.is_resolvable,
                resolved_at   = NOW(),
                expires_at    = EXCLUDED.expires_at
        """
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    sql,
                    ticker,
                    metadata.get("company_name"),
                    metadata.get("exchange"),
                    metadata.get("sector"),
                    metadata.get("industry"),
                    metadata.get("currency"),
                    metadata.get("country"),
                    is_resolvable,
                    expires_at,
                )
        except asyncpg.PostgresError as exc:
            raise ExternalProviderError(
                f"Failed to upsert ticker cache for {ticker}: {exc}",
                error_code="DB_TICKER_CACHE_WRITE_ERROR",
                user_message="Ticker cache write failed.",
                is_retryable=True,
            ) from exc
