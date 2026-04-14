"""Hybrid market data provider: nse + alpha vantage"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.domain.models.market import CompanyInfo, MarketData, PriceHistory
from app.infrastructure.providers.market_data_alpha_vantage import AlphaVantageDataProvider
from app.infrastructure.providers.market_data_nse import NSEMarketDataProvider
from app.infrastructure.providers.market_data_yfinance import (
    GLOBAL_SUFFIXES,
    INDIAN_SUFFIXES,
    MarketType,
    YFinanceDataProvider,
)

if TYPE_CHECKING:
    import redis.asyncio as aioredis

    from app.config import Settings

logger = logging.getLogger(__name__)


class HybridMarketDataProvider:
    """Multi-source market data provider with intelligent fallback.

    1. NSE API (for Indian stocks)
    2. Alpha Vantage (for price history)
    """

    def __init__(
        self,
        redis: aioredis.Redis,  # type: ignore[type-arg]
        settings: Settings,
    ) -> None:
        """Initialize providers."""
        self._yfinance = YFinanceDataProvider()
        self._nse = NSEMarketDataProvider()
        self._alpha_vantage = AlphaVantageDataProvider(
            api_key=getattr(settings, "alpha_vantage_api_key", None)
        )
        self._redis = redis
        self._settings = settings

    async def get_quote(self, ticker: str) -> MarketData | None:
        """Get quote, trying providers in order."""
        market = await self._classify_market(ticker)

        if not market:
            return None

        if market == "IN" and "." not in ticker:
            ticker = ticker + ".NS"

        quote = await self._alpha_vantage.get_quote(ticker)
        if quote:
            logger.info("get_quote(%s) — success via Alpha Vantage provider", ticker)
            return quote

        logger.info("get_quote(%s) — alpha vantage provider failed", ticker)

        if market == "IN":
            quote = await self._nse.get_quote(ticker)
            if quote:
                logger.info("get_quote(%s) — success via NSE provider", ticker)
                return quote
            logger.info("get_quote(%s) — NSE provider failed", ticker)

        quote = await self._yfinance.get_quote(ticker)
        if quote:
            logger.info("get_quote(%s) — success via yfinance provider", ticker)
            return quote

        logger.warning("get_quote(%s) — all providers failed", ticker)
        return None

    async def get_price_history(self, ticker: str, period: str = "3mo") -> PriceHistory | None:
        """Get price history, trying providers in order."""
        market = await self._classify_market(ticker)

        if not market:
            return None

        if market == "IN" and "." not in ticker:
            ticker = ticker + ".NS"

        history = await self._yfinance.get_price_history(ticker, period)
        if history:
            logger.info("get_price_history(%s, %s) — success via yfinance", ticker, period)
            return history

        logger.info(
            "get_price_history(%s, %s) — yfinance provider failed. retrying with alpha vantage",
            ticker,
            period,
        )

        history = await self._alpha_vantage.get_price_history(ticker, period)
        if history:
            logger.info("get_price_history(%s, %s) — success via Alpha Vantage", ticker, period)
            return history

        logger.warning("get_price_history(%s, %s) — all providers failed", ticker, period)
        return None

    async def get_company_info(self, ticker: str) -> CompanyInfo | None:
        """Get company info, trying providers in order."""
        market = await self._classify_market(ticker)

        if not market:
            return None

        if market == "IN" and "." not in ticker:
            ticker = ticker + ".NS"

        if market == "IN":
            info = await self._nse.get_company_info(ticker)
            if info:
                logger.info("get_company_info(%s) — success via NSE provider", ticker)
                return info

            logger.info(
                "get_company_info(%s) — NSE provider failed. retrying with yfinance", ticker
            )

            info = await self._yfinance.get_company_info(ticker)
            if info:
                logger.info("get_company_info(%s) — success via yfinance provider", ticker)
                return info

            logger.info(
                "get_company_info(%s) — yfinance provider failed. retrying with alpha vantage",
                ticker,
            )

            info = await self._alpha_vantage.get_company_info(ticker)
            if info:
                logger.info("get_company_info(%s) — success via alpha vantage provider", ticker)
                return info
        else:
            info = await self._alpha_vantage.get_company_info(ticker)
            if info:
                logger.info("get_company_info(%s) — success via alpha vantage provider", ticker)
                return info

            logger.info(
                "get_company_info(%s) — alpha vantage provider failed. retrying with yfinance",
                ticker,
            )

            info = await self._yfinance.get_company_info(ticker)
            if info:
                logger.info("get_company_info(%s) — success via yfinance provider", ticker)
                return info

        logger.warning("get_company_info(%s) — all providers failed", ticker)
        return None

    async def is_ticker_resolvable(self, ticker: str) -> bool:
        """Check if ticker is resolvable via any provider."""
        market = await self._classify_market(ticker)
        return market is not None

    async def _classify_market(self, ticker: str) -> MarketType | None:
        ticker = ticker.upper()

        if "." in ticker:
            base, suffix = ticker.rsplit(".", 1)
            symbol = base.upper()
            suffix = f".{suffix.upper()}"
        else:
            symbol = ticker
            suffix = None

        if suffix:
            if suffix in INDIAN_SUFFIXES:
                return "IN"
            if suffix in GLOBAL_SUFFIXES:
                return "GLOBAL"
            return None

        if await self._redis.sismember("symbols:india", symbol):
            return "IN"

        if await self._redis.sismember("symbols:global", symbol):
            return "GLOBAL"

        market = await self._yfinance.search_ticker_exists(symbol)

        if market:
            if market == "IN":
                await self._redis.sadd("symbols:india", symbol)
            else:
                await self._redis.sadd("symbols:global", symbol)

            return market

        return None
