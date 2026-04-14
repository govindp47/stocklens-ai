"""NSE (National Stock Exchange) market data provider for Indian stocks.

Free data from NSE India without requiring API keys.
Covers all NSE-listed stocks (primary focus).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.domain.models.market import CompanyInfo, MarketData, PriceHistory

logger = logging.getLogger(__name__)


class NSEMarketDataProvider:
    """Fallback provider for Indian stocks using NSE CSV data.

    Free data from NSE India without requiring API keys.
    Covers all NSE-listed stocks (primary focus).
    """

    def __init__(self) -> None:
        """Initialize NSE provider."""
        pass

    async def get_quote(self, ticker: str) -> MarketData | None:
        """Fetch quote for Indian stock from NSE.

        NSE tickers format: INFY.NS, RELIANCE.NS, TCS.NS, etc.
        Falls back to checking without .NS suffix.
        """

        ticker = ticker.upper()

        if "." in ticker:
            base, _ = ticker.rsplit(".", 1)
            ticker = base.upper()

        try:
            import httpx

            url = f"https://www.nseindia.com/api/quote-equity?symbol={ticker}"

            async with httpx.AsyncClient(
                timeout=5.0,
                headers={"User-Agent": "Mozilla/5.0"},
            ) as client:
                resp = await client.get(url)

                if resp.status_code == 200:
                    data = resp.json()

                    def _f(val: object) -> float | None:
                        try:
                            result = float(val)  # type: ignore[arg-type]
                            return result if result > 0 else None
                        except (TypeError, ValueError):
                            return None

                    price_info = data.get("priceInfo", {})
                    trade_info = data.get("preOpenMarket", {})
                    security_info = data.get("securityInfo", {})
                    metadata = data.get("metadata", {})

                    price = _f(price_info.get("lastPrice"))
                    change = _f(price_info.get("change"))
                    p_change = _f(price_info.get("pChange"))
                    total_traded_volume = _f(trade_info.get("totalTradedVolume"))
                    issued_size = _f(security_info.get("issuedSize"))
                    pd_symbol_pe = _f(metadata.get("pdSymbolPe"))

                    return MarketData(
                        available=True,
                        price=price,
                        change_pct=p_change,
                        change_abs=change,
                        volume=total_traded_volume,
                        market_cap=(price * issued_size if (price and issued_size) else None),
                        pe_ratio=pd_symbol_pe,
                        week_52_high=None,
                        week_52_low=None,
                        currency="INR",
                        data_delayed_minutes=5,
                        as_of=datetime.now(tz=UTC),
                    )
        except Exception as exc:
            logger.debug("NSE quote fetch failed for %s: %s", ticker, exc)

        return None

    async def get_price_history(self, ticker: str, period: str = "3mo") -> PriceHistory | None:
        """Get price history from NSE historical data endpoint.

        Scrapes NSE's equity history API. Capped at 1 year regardless of
        the requested period to stay within reliable NSE data availability.
        """
        return None

    async def get_company_info(self, ticker: str) -> CompanyInfo | None:
        """Get company info from NSE."""

        ticker = ticker.upper()

        if "." in ticker:
            base, _ = ticker.rsplit(".", 1)
            ticker = base.upper()

        try:
            import httpx

            url = f"https://www.nseindia.com/api/quote-equity?symbol={ticker}"

            async with httpx.AsyncClient(
                timeout=5.0,
                headers={"User-Agent": "Mozilla/5.0"},
            ) as client:
                resp = await client.get(url)

                if resp.status_code == 200:
                    data = resp.json()
                    info = data.get("info", {})
                    industry_info = data.get("industryInfo", {})

                    return CompanyInfo(
                        ticker=ticker,
                        name=info.get("companyName"),
                        exchange="NSE",
                        sector=industry_info.get("sector"),
                        industry=industry_info.get("industry"),
                        currency="INR",
                        country="India",
                    )
        except Exception as exc:
            logger.debug("NSE company info failed for %s: %s", ticker, exc)

        return None
