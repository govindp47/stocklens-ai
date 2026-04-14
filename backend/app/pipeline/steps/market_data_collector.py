"""Step 2 — MarketDataCollector (non-critical pipeline step).

Fetches the current market quote and 3-month price history concurrently via
YFinanceMarketDataProvider.  Trend direction is computed by linear regression
on the last 20 closing prices using only Python stdlib (no numpy).
Volatility flag is set when the standard deviation of daily returns exceeds 3%.

This is a non-critical step: failure is recorded and the pipeline continues.
"""

from __future__ import annotations

import asyncio
import logging
import statistics
import time

from app.domain.models.market import PriceHistory, PricePoint
from app.infrastructure.providers.market_data_provider import MarketDataProvider
from app.pipeline.context import PipelineContext
from app.pipeline.steps.base import BasePipelineStep, StepResult, StepStatus

logger = logging.getLogger(__name__)

# Maximum number of closing prices used for regression (sliding window)
_REGRESSION_WINDOW: int = 20

# Trend threshold: ±0.5 % of mean price per day (from 04_DOMAIN_ENGINE_DESIGN.md § Step 2)
_TREND_THRESHOLD_PCT: float = 0.005


# ── Pure statistical helpers (stdlib only) ────────────────────────────────────


def _compute_trend_direction(datapoints: list[PricePoint]) -> str | None:
    """Return 'upward', 'downward', or 'sideways' via OLS slope on closing prices.

    Uses ``statistics.linear_regression`` (Python 3.10+).  Returns None when
    fewer than 2 non-null closing prices are available.

    Threshold: ±0.5% of mean closing price per day, per the domain spec.
    """
    closes = [p.close for p in datapoints if p.close is not None]
    window = closes[-_REGRESSION_WINDOW:]  # last ≤ 20 prices
    if len(window) < 2:
        return None

    x = list(range(len(window)))
    regression = statistics.linear_regression(x, window)
    slope: float = regression.slope

    mean_price = statistics.mean(window)
    threshold = _TREND_THRESHOLD_PCT * mean_price

    if slope > threshold:
        return "upward"
    if slope < -threshold:
        return "downward"
    return "sideways"


def _compute_volatility_flag(datapoints: list[PricePoint]) -> bool:
    """Return True if stdev of daily returns exceeds 3 %.

    Requires at least 3 closing prices to produce at least 2 return values
    for a meaningful stdev computation.
    """
    closes = [p.close for p in datapoints if p.close is not None]
    if len(closes) < 3:  # need at least 2 return values
        return False

    daily_returns = [
        (closes[i] - closes[i - 1]) / closes[i - 1]
        for i in range(1, len(closes))
        if closes[i - 1] != 0.0
    ]
    if len(daily_returns) < 2:
        return False

    return statistics.stdev(daily_returns) > 0.03


# ── Step ──────────────────────────────────────────────────────────────────────


class MarketDataCollector(BasePipelineStep):
    """Collect market quote and OHLCV history; derive trend and volatility metrics.

    Attributes:
        name: Step identifier used in logging, metrics, and persistence.
        step_index: Execution order index (2 = second step).
        critical: False — failure is recorded; downstream steps may still run.
        max_retries: 2 — transient yfinance/network errors are retried.
    """

    name: str = "MarketDataCollector"
    step_index: int = 2
    critical: bool = False
    max_retries: int = 2

    def __init__(self, market_data_provider: MarketDataProvider) -> None:
        self._provider = market_data_provider

    # ──────────────────────────────────────────────────────────────────────
    # PipelineStep Protocol
    # ──────────────────────────────────────────────────────────────────────

    def can_execute(self, context: PipelineContext) -> bool:
        """Requires Step 1 (TickerValidator) to have populated company_info."""
        return context.outputs.has_company_info()

    async def execute(self, context: PipelineContext) -> StepResult:
        """Fetch market data concurrently and populate context outputs.

        Both get_quote and get_price_history are dispatched simultaneously via
        asyncio.gather so they run in separate thread-executor slots.

        Returns:
            StepResult(COMPLETE) — quote and history available.
            StepResult(FAILED)   — quote unavailable (non-critical; pipeline continues).
        """
        ticker = context.ticker
        start_ms = int(time.monotonic() * 1000)

        logger.info("Fetching market data", extra={"ticker": ticker})

        quote, raw_history = await asyncio.gather(
            self._provider.get_quote(ticker),
            self._provider.get_price_history(ticker),
        )

        if quote is None:
            duration_ms = int(time.monotonic() * 1000) - start_ms
            logger.warning("Market quote unavailable", extra={"ticker": ticker})
            return StepResult(
                step_name=self.name,
                step_index=self.step_index,
                status=StepStatus.FAILED,
                duration_ms=duration_ms,
                output_summary="MARKET_DATA_UNAVAILABLE: market provider returned no quote data",
            )

        context.outputs.market_data = quote

        if raw_history is not None and raw_history.datapoints:
            enriched_history = self._enrich_history(raw_history)
            context.outputs.price_history = enriched_history
        else:
            context.outputs.price_history = raw_history  # may be None

        duration_ms = int(time.monotonic() * 1000) - start_ms
        history_points = (
            len(context.outputs.price_history.datapoints) if context.outputs.price_history else 0
        )
        trend = (
            context.outputs.price_history.trend_direction
            if context.outputs.price_history
            else "N/A"
        )
        logger.info(
            "Market data collected",
            extra={
                "ticker": ticker,
                "price": quote.price,
                "history_points": history_points,
                "trend": trend,
                "duration_ms": duration_ms,
            },
        )
        return StepResult(
            step_name=self.name,
            step_index=self.step_index,
            status=StepStatus.COMPLETE,
            duration_ms=duration_ms,
            output_summary=(f"price={quote.price} trend={trend} points={history_points}"),
        )

    # ──────────────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────────────

    def _enrich_history(self, history: PriceHistory) -> PriceHistory:
        """Recompute trend_direction and volatility_flag via regression/stdev.

        Returns a new (frozen) PriceHistory instance with updated metrics,
        replacing the simpler estimates computed by the provider.
        """
        trend = _compute_trend_direction(history.datapoints)
        volatile = _compute_volatility_flag(history.datapoints)
        return PriceHistory(
            available=history.available,
            datapoints=history.datapoints,
            trend_direction=trend,
            volatility_flag=volatile,
        )
