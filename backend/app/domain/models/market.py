"""Market data domain models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CompanyInfo(BaseModel):
    """Resolved company metadata for a ticker symbol."""

    model_config = ConfigDict(frozen=True)

    ticker: str
    name: str | None = None
    exchange: str | None = None
    sector: str | None = None
    industry: str | None = None
    currency: str | None = None
    country: str | None = None


class MarketData(BaseModel):
    """Current market quote and key financial ratios for a ticker.

    All numeric fields are float | None — never raise on missing yfinance data.
    """

    model_config = ConfigDict(frozen=True)

    available: bool = False
    price: float | None = None
    change_pct: float | None = None
    change_abs: float | None = None
    volume: float | None = None
    market_cap: float | None = None
    pe_ratio: float | None = None
    week_52_high: float | None = None
    week_52_low: float | None = None
    currency: str = "USD"
    data_delayed_minutes: int = 15
    as_of: datetime | None = None


class PricePoint(BaseModel):
    """Single OHLCV data point in a price history series."""

    model_config = ConfigDict(frozen=True)

    date: str  # ISO 8601: YYYY-MM-DD
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None


class PriceHistory(BaseModel):
    """3-month OHLCV price history for a ticker."""

    model_config = ConfigDict(frozen=True)

    available: bool = False
    datapoints: list[PricePoint] = []
    trend_direction: str | None = None  # e.g. "up", "down", "flat"
    volatility_flag: bool = False
