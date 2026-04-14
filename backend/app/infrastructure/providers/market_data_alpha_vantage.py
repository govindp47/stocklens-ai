"""Alpha Vantage market data provider (free tier fallback)."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.domain.models.market import CompanyInfo, MarketData, PriceHistory, PricePoint

if TYPE_CHECKING:
    import httpx

logger = logging.getLogger(__name__)

# Minimum seconds between any two Alpha Vantage API calls (free tier: 5 req/min)
_MIN_CALL_INTERVAL: float = 2.0

# Module-level lock and timestamp shared across all provider instances
_api_lock: asyncio.Lock = asyncio.Lock()
_last_call_time: float = 0.0


async def _rate_limited_get(
    client: httpx.AsyncClient, url: str, params: dict[str, str]
) -> httpx.Response:
    """Acquire the global AV rate-limit lock, wait if needed, then GET."""
    global _last_call_time
    async with _api_lock:
        elapsed = time.monotonic() - _last_call_time
        if elapsed < _MIN_CALL_INTERVAL:
            await asyncio.sleep(_MIN_CALL_INTERVAL - elapsed)
        _last_call_time = time.monotonic()
        return await client.get(url, params=params)


class AlphaVantageDataProvider:
    """Fallback provider using Alpha Vantage free tier (if key available).

    Supports both US and Indian stocks.
    Free tier: 5 requests/min, 25 requests/day.

    A module-level rate limiter ensures at least 2 seconds between consecutive
    API calls regardless of how many provider instances exist.
    """

    def __init__(self, api_key: str | None = None) -> None:
        """Initialize with optional API key."""
        self.api_key = api_key or ""
        self.base_url = "https://www.alphavantage.co/query"

    async def _fetch_global_quote(self, client: httpx.AsyncClient, ticker: str) -> dict[str, Any]:
        """Call GLOBAL_QUOTE endpoint and return the 'Global Quote' dict."""
        params = {
            "function": "GLOBAL_QUOTE",
            "symbol": ticker,
            "apikey": self.api_key,
        }
        resp = await _rate_limited_get(client, self.base_url, params)
        if resp.status_code != 200:
            return {}
        data: Any = resp.json()
        if "Error Message" in data or "Information" in data:
            return {}
        result = data.get("Global Quote", {})
        return result if isinstance(result, dict) else {}

    async def _fetch_overview(self, client: httpx.AsyncClient, ticker: str) -> dict[str, Any]:
        """Call OVERVIEW endpoint and return the raw data dict."""
        params = {
            "function": "OVERVIEW",
            "symbol": ticker,
            "apikey": self.api_key,
        }
        resp = await _rate_limited_get(client, self.base_url, params)
        if resp.status_code != 200:
            return {}
        data: Any = resp.json()
        if "Error Message" in data or "Information" in data:
            return {}
        return data if isinstance(data, dict) else {}

    async def get_quote(self, ticker: str) -> MarketData | None:
        """Fetch full quote using GLOBAL_QUOTE + OVERVIEW endpoints.

        GLOBAL_QUOTE provides: price, change_pct, change_abs, volume, week_52_high/low.
        OVERVIEW provides: market_cap, pe_ratio, currency.
        """
        if not self.api_key:
            logger.debug("Alpha Vantage API key not configured")
            return None

        ticker = ticker.upper()

        if "." in ticker:
            base, _ = ticker.rsplit(".", 1)
            ticker = base.upper()

        try:
            import httpx

            async with httpx.AsyncClient(
                timeout=10.0,
                headers={"User-Agent": "Mozilla/5.0"},
            ) as client:
                quote = await self._fetch_global_quote(client, ticker)
                if not quote:
                    return None

                overview = await self._fetch_overview(client, ticker)

            def _f(val: object) -> float | None:
                try:
                    result = float(val)  # type: ignore[arg-type]
                    return result if result > 0 else None
                except (TypeError, ValueError):
                    return None

            price = _f(quote.get("05. price"))
            change_pct_str = quote.get("10. change percent", "0%")
            if isinstance(change_pct_str, str):
                change_pct = _f(change_pct_str.rstrip("%"))
            else:
                change_pct = _f(change_pct_str)
            change = _f(quote.get("09. change"))
            volume = _f(quote.get("06. volume"))
            market_cap = _f(overview.get("MarketCapitalization"))
            pe_ratio = _f(overview.get("PERatio"))
            week_52_high = _f(overview.get("52WeekHigh"))
            week_52_low = _f(overview.get("52WeekLow"))
            currency_val = overview.get("Currency")
            currency = currency_val if isinstance(currency_val, str) else "USD"

            return MarketData(
                available=True,
                price=price,
                change_pct=change_pct,
                change_abs=change,
                volume=volume,
                market_cap=market_cap,
                pe_ratio=pe_ratio,
                week_52_high=week_52_high,
                week_52_low=week_52_low,
                currency=currency,
                data_delayed_minutes=15,
                as_of=datetime.now(tz=UTC),
            )
        except Exception as exc:
            logger.debug("Alpha Vantage quote failed for %s: %s", ticker, exc)

        return None

    async def get_price_history(self, ticker: str, period: str = "3mo") -> PriceHistory | None:
        """Get daily price history from Alpha Vantage."""
        if not self.api_key:
            logger.debug("Alpha Vantage API key not configured")
            return None

        ticker = ticker.upper()

        if "." in ticker:
            base, _ = ticker.rsplit(".", 1)
            ticker = base.upper()

        try:
            import httpx

            params = {
                "function": "TIME_SERIES_DAILY",
                "symbol": ticker,
                "apikey": self.api_key,
                # "outputsize": "full", # for premium
            }

            async with httpx.AsyncClient(
                timeout=10.0,
                headers={"User-Agent": "Mozilla/5.0"},
            ) as client:
                resp = await _rate_limited_get(client, self.base_url, params)

                if resp.status_code != 200:
                    return None

                data = resp.json()

                if (
                    "Error Message" in data
                    or "Information" in data
                    or "Time Series (Daily)" not in data
                ):
                    return None

                ts = data.get("Time Series (Daily)", {})
                datapoints: list[PricePoint] = []

                for date_str, ohlc in sorted(ts.items(), reverse=True):
                    datapoints.append(
                        PricePoint(
                            date=date_str,
                            open=float(ohlc.get("1. open") or 0) or None,
                            high=float(ohlc.get("2. high") or 0) or None,
                            low=float(ohlc.get("3. low") or 0) or None,
                            close=float(ohlc.get("4. close") or 0) or None,
                            volume=float(ohlc.get("5. volume") or 0) or None,
                        )
                    )

                if not datapoints:
                    return None

                return PriceHistory(
                    available=True,
                    datapoints=list(reversed(datapoints)),
                    trend_direction=None,
                    volatility_flag=False,
                )
        except Exception as exc:
            logger.debug("Alpha Vantage history failed for %s: %s", ticker, exc)

        return None

    async def get_company_info(self, ticker: str) -> CompanyInfo | None:
        """Get company info from Alpha Vantage OVERVIEW endpoint."""
        if not self.api_key:
            logger.debug("Alpha Vantage API key not configured")
            return None

        ticker = ticker.upper()

        if "." in ticker:
            base, _ = ticker.rsplit(".", 1)
            ticker = base.upper()

        try:
            import httpx

            async with httpx.AsyncClient(
                timeout=10.0,
                headers={"User-Agent": "Mozilla/5.0"},
            ) as client:
                data = await self._fetch_overview(client, ticker)

            if not data:
                return None

            ticker_val = data.get("Symbol")
            if not isinstance(ticker_val, str):
                return None

            return CompanyInfo(
                ticker=ticker_val,
                name=data.get("Name"),
                exchange=data.get("Exchange"),
                sector=data.get("Sector"),
                industry=data.get("Industry"),
                currency=data.get("Currency"),
                country=data.get("Country"),
            )
        except Exception as exc:
            logger.debug("Alpha Vantage company info failed for %s: %s", ticker, exc)

        return None
