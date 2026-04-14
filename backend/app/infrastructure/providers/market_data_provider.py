"""Market data provider protocol and re-exports.

The concrete implementations live in their own modules:
- YFinanceMarketDataProvider → market_data_yfinance.py
- NSEMarketDataProvider      → market_data_nse.py
- AlphaVantageProvider       → market_data_alpha_vantage.py
- HybridMarketDataProvider   → market_data_hybrid.py
"""

from __future__ import annotations

from typing import Protocol

from app.domain.models.market import CompanyInfo, MarketData, PriceHistory


class MarketDataProvider(Protocol):
    """Protocol defining the market data provider interface."""

    async def get_quote(self, ticker: str) -> MarketData | None:
        """Get current market quote for ticker."""
        ...

    async def get_price_history(self, ticker: str, period: str = "3mo") -> PriceHistory | None:
        """Get historical price data for ticker."""
        ...

    async def get_company_info(self, ticker: str) -> CompanyInfo | None:
        """Get company information for ticker."""
        ...

    async def is_ticker_resolvable(self, ticker: str) -> bool:
        """Check if ticker resolves to a known security."""
        ...
