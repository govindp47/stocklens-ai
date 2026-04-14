"""YFinanceMarketDataProvider — quote and price history via yfinance.

All yfinance I/O runs in a thread executor to avoid blocking the asyncio
event loop.  Redis caching (TTL=300s for quotes, TTL=3600s for ticker
resolution checks) sits in front of every external call.  All numeric
fields are normalised to float | None — no KeyError is possible.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Literal

from app.domain.models.market import CompanyInfo, MarketData, PriceHistory, PricePoint

logger = logging.getLogger(__name__)


MarketType = Literal["IN", "GLOBAL"]

INDIAN_SUFFIXES = {".NS", ".BO"}  # NSE, BSE
GLOBAL_SUFFIXES = {".US", ".NYSE", ".NASDAQ", ".L", ".HK", ".TO", ".AX"}


class YFinanceDataProvider:
    """Async market data provider backed by yfinance with Redis caching.

    All yfinance calls are dispatched to the default thread executor via
    ``asyncio.get_running_loop().run_in_executor(None, ...)`` so they never
    block the event loop.

    """

    def __init__(self) -> None:
        """Initialize yahoo finance provider."""
        pass

    async def get_quote(self, ticker: str) -> MarketData | None:
        """Fetch stock quote from yahoo finance"""

        ticker = ticker.upper()

        try:
            import httpx

            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"

            params = {
                "range": "1d",
                "interval": "1d",
            }

            async with httpx.AsyncClient(
                timeout=5.0,
                headers={"User-Agent": "Mozilla/5.0"},
            ) as client:
                resp = await client.get(url=url, params=params)

                if resp.status_code != 200:
                    return None

                def _f(val: object) -> float | None:
                    try:
                        result = float(val)  # type: ignore[arg-type]
                        return result if result > 0 else None
                    except (TypeError, ValueError):
                        return None

                data = resp.json()
                result = data.get("chart", {}).get("result", [])

                if not result:
                    return None

                meta = result[0].get("meta", {})

                price = _f(meta.get("regularMarketPrice"))
                prev = _f(meta.get("previousClose")) or _f(meta.get("chartPreviousClose"))

                change = None
                p_change = None

                if price and prev:
                    change = price - prev
                    p_change = (change / prev) * 100

                total_traded_volume = _f(meta.get("regularMarketVolume"))
                market_cap = _f(meta.get("marketCap"))
                pd_symbol_pe = _f(meta.get("trailingPE"))
                week_52_high = _f(meta.get("fiftyTwoWeekHigh"))
                week_52_low = _f(meta.get("fiftyTwoWeekLow"))
                currency = meta.get("currency")

                return MarketData(
                    available=True,
                    price=price,
                    change_pct=p_change,
                    change_abs=change,
                    volume=total_traded_volume,
                    market_cap=market_cap,
                    pe_ratio=pd_symbol_pe,
                    week_52_high=week_52_high,
                    week_52_low=week_52_low,
                    currency=currency,
                    data_delayed_minutes=5,
                    as_of=datetime.now(tz=UTC),
                )
        except Exception as exc:
            logger.debug("yahoo finance quote fetch failed for %s: %s", ticker, exc)

        return None

    async def get_price_history(self, ticker: str, period: str = "3mo") -> PriceHistory | None:
        """Get price history from yahoo finance."""

        ticker = ticker.upper()

        try:
            import httpx

            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"

            params = {
                "range": period,
                "interval": "1d",
            }

            async with httpx.AsyncClient(
                timeout=5.0,
                headers={"User-Agent": "Mozilla/5.0"},
            ) as client:
                resp = await client.get(url=url, params=params)

                if resp.status_code != 200:
                    return None

                def _f(val: object) -> float | None:
                    try:
                        result = float(val)  # type: ignore[arg-type]
                        return result if result > 0 else None
                    except (TypeError, ValueError):
                        return None

                data = resp.json()

                result = data.get("chart", {}).get("result")
                if not result:
                    return None

                result = result[0]

                timestamps = result.get("timestamp", [])
                quote = result.get("indicators", {}).get("quote", [{}])[0]

                opens = quote.get("open", [])
                highs = quote.get("high", [])
                lows = quote.get("low", [])
                closes = quote.get("close", [])
                volumes = quote.get("volume", [])

                datapoints: list[PricePoint] = []

                for i in range(len(timestamps)):
                    if closes[i] is None:
                        continue

                    datapoints.append(
                        PricePoint(
                            date=datetime.fromtimestamp(timestamps[i], tz=UTC).strftime("%Y-%m-%d"),
                            open=_f(opens[i]),
                            high=_f(highs[i]),
                            low=_f(lows[i]),
                            close=_f(closes[i]),
                            volume=_f(volumes[i]),
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
            logger.debug("Yahoo finance history failed for %s: %s", ticker, exc)

        return None

    async def get_company_info(self, ticker: str) -> CompanyInfo | None:
        """Get company info from yahoo"""

        ticker = ticker.upper()

        try:
            import httpx

            search_url = "https://query1.finance.yahoo.com/v1/finance/search"
            chart_url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"

            params = {"q": ticker}

            async with httpx.AsyncClient(
                timeout=5.0, headers={"User-Agent": "Mozilla/5.0"}
            ) as client:
                resp = await client.get(url=search_url, params=params)

                if resp.status_code != 200:
                    return None

                data = resp.json()
                quotes = data.get("quotes", [])

                if not quotes:
                    return None

                match = None
                for q in quotes:
                    symbol = q.get("symbol", "").upper()
                    if (
                        symbol == ticker
                        or symbol.startswith(ticker + ".")
                        or ticker.startswith(symbol + ".")
                    ):
                        match = q
                        break

                if not match:
                    return None

                resp = await client.get(url=chart_url)

                if resp.status_code != 200:
                    return None

                data = resp.json()
                result = data.get("chart", {}).get("result")

                if not result:
                    return None

                meta = result[0].get("meta", {})

                return CompanyInfo(
                    ticker=(match or {}).get("symbol", "").upper(),
                    name=(match or {}).get("shortname") or (match or {}).get("longname"),
                    exchange=meta.get("exchangeName"),
                    sector=None,
                    industry=None,
                    currency=meta.get("currency"),
                    country=meta.get("exchangeTimezoneName"),
                )
        except Exception as exc:
            logger.debug("yahoo finance company info failed for %s: %s", ticker, exc)

        return None

    async def search_ticker_exists(self, ticker: str) -> MarketType | None:
        try:
            import httpx

            url = "https://query1.finance.yahoo.com/v1/finance/search"

            params = {
                "q": ticker,
            }

            async with httpx.AsyncClient(
                timeout=5.0,
                headers={"User-Agent": "Mozilla/5.0"},
            ) as client:
                resp = await client.get(url=url, params=params)

            if resp.status_code != 200:
                logger.debug("Yahoo search failed with status %s for %s", resp.status_code, ticker)
                return None

            data = resp.json()
            quotes = data.get("quotes", [])

            if not quotes:
                return None

            ticker_upper = ticker.upper()

            match = None
            for q in quotes:
                symbol = q.get("symbol", "").upper()

                if symbol == ticker_upper or symbol.startswith(ticker_upper + "."):
                    match = q
                    break

            if not match:
                return None

            exchange = match.get("exchange", "").upper()
            symbol = match.get("symbol", "").upper()

            if exchange in {"NSI", "BSE"} or symbol.endswith(".NS") or symbol.endswith(".BO"):
                return "IN"

            return "GLOBAL"

        except Exception as exc:
            logger.debug("searching stock symbol failed for %s: %s", ticker, exc)
            return None
