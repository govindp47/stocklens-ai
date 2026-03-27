"""YFinanceMarketDataProvider — quote and price history via yfinance.

All yfinance I/O runs in a thread executor to avoid blocking the asyncio
event loop.  Redis caching (TTL=300s for quotes, TTL=3600s for ticker
resolution checks) sits in front of every external call.  All numeric
fields are normalised to float | None — no KeyError is possible.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis
import yfinance as yf

from app.config import Settings
from app.domain.models.market import CompanyInfo, MarketData, PriceHistory, PricePoint
from app.infrastructure.cache import cache_get, cache_set

logger = logging.getLogger(__name__)

_QUOTE_TTL: int = 300     # 5 minutes
_RESOLVE_TTL: int = 3_600  # 1 hour


def _safe_float(value: Any) -> float | None:
    """Coerce *value* to float, returning None on failure or negative-sentinel."""
    if value is None:
        return None
    try:
        result = float(value)
        return result if result == result else None  # NaN guard  # noqa: PLR0124
    except (TypeError, ValueError):
        return None


def _normalize_pe(value: Any) -> float | None:
    """Return None for negative or missing P/E ratios."""
    fval = _safe_float(value)
    if fval is None or fval < 0:
        return None
    return fval


def _trend_direction(datapoints: list[PricePoint]) -> str | None:
    """Derive trend direction from first/last closing prices."""
    closes = [p.close for p in datapoints if p.close is not None]
    if len(closes) < 2:
        return None
    delta = closes[-1] - closes[0]
    pct = delta / closes[0] if closes[0] != 0 else 0.0
    if pct > 0.01:
        return "up"
    if pct < -0.01:
        return "down"
    return "flat"


def _volatility_flag(datapoints: list[PricePoint]) -> bool:
    """Return True if the annualised daily return std-dev exceeds 3 %."""
    closes = [p.close for p in datapoints if p.close is not None]
    if len(closes) < 5:
        return False
    returns = [
        (closes[i] - closes[i - 1]) / closes[i - 1]
        for i in range(1, len(closes))
        if closes[i - 1] != 0
    ]
    if not returns:
        return False
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / len(returns)
    std_dev = math.sqrt(variance)
    return std_dev > 0.03


class YFinanceMarketDataProvider:
    """Async market data provider backed by yfinance with Redis caching.

    All yfinance calls are dispatched to the default thread executor via
    ``asyncio.get_running_loop().run_in_executor(None, ...)`` so they never
    block the event loop.
    """

    def __init__(
        self,
        redis: aioredis.Redis,  # type: ignore[type-arg]
        settings: Settings,
    ) -> None:
        self._redis = redis
        self._settings = settings

    # ──────────────────────────────────────────────────────────────────────
    # Public interface
    # ──────────────────────────────────────────────────────────────────────

    async def get_quote(self, ticker: str) -> MarketData | None:
        """Return a normalised MarketData snapshot for *ticker*.

        Checks Redis first.  On cache miss, fetches yfinance.Ticker.info in
        a thread executor, normalises the result, caches it, and returns it.
        Returns None when yfinance returns an empty or unusable info dict.
        """
        cache_key = f"market_data:quote:{ticker}"
        cached = await cache_get(self._redis, cache_key)
        if cached is not None:
            try:
                data = json.loads(cached)
                return MarketData(**data)
            except Exception:
                logger.warning("Corrupt quote cache entry; re-fetching", extra={"ticker": ticker})

        info = await self._fetch_info(ticker)
        if not info or not info.get("regularMarketPrice"):
            logger.debug("yfinance returned empty info for %s", ticker)
            return None

        market_data = self._normalize_quote(info)
        try:
            await cache_set(self._redis, cache_key, market_data.model_dump_json(), _QUOTE_TTL)
        except Exception:
            pass  # cache write failure is non-fatal
        return market_data

    async def get_price_history(
        self, ticker: str, period: str = "3mo"
    ) -> PriceHistory | None:
        """Return OHLCV history for *ticker* over *period*.

        Runs yfinance.Ticker.history(auto_adjust=True) in a thread executor.
        Timestamps are converted to ISO date strings (YYYY-MM-DD).
        Returns None when yfinance returns an empty DataFrame.
        """
        loop = asyncio.get_running_loop()
        try:
            df = await loop.run_in_executor(
                None,
                lambda: yf.Ticker(ticker).history(period=period, auto_adjust=True),
            )
        except Exception as exc:
            logger.warning("yfinance history error for %s: %s", ticker, exc)
            return None

        if df is None or df.empty:
            return None

        datapoints: list[PricePoint] = []
        for ts, row in df.iterrows():
            date_str: str = ts.strftime("%Y-%m-%d")
            datapoints.append(
                PricePoint(
                    date=date_str,
                    open=_safe_float(row.get("Open")),
                    high=_safe_float(row.get("High")),
                    low=_safe_float(row.get("Low")),
                    close=_safe_float(row.get("Close")),
                    volume=_safe_float(row.get("Volume")),
                )
            )

        return PriceHistory(
            available=True,
            datapoints=datapoints,
            trend_direction=_trend_direction(datapoints),
            volatility_flag=_volatility_flag(datapoints),
        )

    async def is_ticker_resolvable(self, ticker: str) -> bool:
        """Return True if *ticker* resolves to a known security on yfinance.

        Checks a dedicated Redis cache (TTL=3600s) before hitting yfinance.
        Returns False (not raises) when yfinance returns empty or unusable data.
        """
        cache_key = f"market_data:resolvable:{ticker}"
        cached = await cache_get(self._redis, cache_key)
        if cached is not None:
            return cached == "1"

        info = await self._fetch_info(ticker)
        resolvable = bool(info and info.get("regularMarketPrice"))

        try:
            await cache_set(
                self._redis, cache_key, "1" if resolvable else "0", _RESOLVE_TTL
            )
        except Exception:
            pass
        return resolvable

    async def get_company_info(self, ticker: str) -> CompanyInfo | None:
        """Return basic CompanyInfo for *ticker* using the cached info dict."""
        info = await self._fetch_info(ticker)
        if not info:
            return None
        return CompanyInfo(
            ticker=ticker,
            name=info.get("longName") or info.get("shortName"),
            exchange=info.get("exchange"),
            sector=info.get("sector"),
            industry=info.get("industry"),
            currency=info.get("currency"),
            country=info.get("country"),
        )

    # ──────────────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────────────

    async def _fetch_info(self, ticker: str) -> dict[str, Any]:
        """Run yfinance.Ticker(ticker).info in a thread executor.

        Returns an empty dict (not raises) on any error.
        """
        loop = asyncio.get_running_loop()
        try:
            info: dict[str, Any] = await loop.run_in_executor(
                None, lambda: yf.Ticker(ticker).info
            )
            return info if isinstance(info, dict) else {}
        except Exception as exc:
            logger.warning("yfinance info error for %s: %s", ticker, exc)
            return {}

    def _normalize_quote(self, info: dict[str, Any]) -> MarketData:
        """Build a normalised MarketData from a raw yfinance info dict."""
        price = _safe_float(info.get("regularMarketPrice"))
        prev_close = _safe_float(info.get("regularMarketPreviousClose"))
        change_abs: float | None = None
        change_pct: float | None = None
        if price is not None and prev_close is not None and prev_close != 0:
            change_abs = price - prev_close
            change_pct = (change_abs / prev_close) * 100.0

        return MarketData(
            available=True,
            price=price,
            change_pct=change_pct,
            change_abs=change_abs,
            volume=_safe_float(info.get("regularMarketVolume")),
            market_cap=_safe_float(info.get("marketCap")),
            pe_ratio=_normalize_pe(info.get("trailingPE")),
            week_52_high=_safe_float(info.get("fiftyTwoWeekHigh")),
            week_52_low=_safe_float(info.get("fiftyTwoWeekLow")),
            currency=info.get("currency") or "USD",
            data_delayed_minutes=15,
            as_of=datetime.now(tz=timezone.utc),
        )
