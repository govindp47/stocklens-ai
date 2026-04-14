"""Unit tests for MarketDataCollector pipeline step (T-024)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.domain.models.market import CompanyInfo, MarketData, PriceHistory, PricePoint
from app.pipeline.context import PipelineContext, PipelineOutputs
from app.pipeline.steps.base import StepStatus
from app.pipeline.steps.market_data_collector import (
    MarketDataCollector,
    _compute_trend_direction,
    _compute_volatility_flag,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_context(
    with_company_info: bool = True,
    ticker: str = "AAPL",
) -> PipelineContext:
    outputs = PipelineOutputs()
    if with_company_info:
        outputs.company_info = CompanyInfo(ticker=ticker, name="Apple Inc.")
    return PipelineContext(
        run_id=uuid4(),
        ticker=ticker,
        llm_provider=MagicMock(),
        outputs=outputs,
    )


def _make_collector(
    quote: MarketData | None = None,
    history: PriceHistory | None = None,
) -> MarketDataCollector:
    mock_provider = MagicMock()
    mock_provider.get_quote = AsyncMock(return_value=quote)
    mock_provider.get_price_history = AsyncMock(return_value=history)
    return MarketDataCollector(market_data_provider=mock_provider)


def _make_datapoints(closes: list[float]) -> list[PricePoint]:
    return [PricePoint(date=f"2024-01-{i+1:02d}", close=c) for i, c in enumerate(closes)]


# ── Metadata ──────────────────────────────────────────────────────────────────


@pytest.mark.unit()
class TestMetadata:
    def test_step_metadata(self) -> None:
        collector = _make_collector()
        assert collector.name == "MarketDataCollector"
        assert collector.step_index == 2
        assert collector.critical is False
        assert collector.max_retries == 2


# ── can_execute ───────────────────────────────────────────────────────────────


@pytest.mark.unit()
class TestCanExecute:
    def test_can_execute_false_without_company_info(self) -> None:
        collector = _make_collector()
        ctx = _make_context(with_company_info=False)
        assert collector.can_execute(ctx) is False

    def test_can_execute_true_with_company_info(self) -> None:
        collector = _make_collector()
        ctx = _make_context(with_company_info=True)
        assert collector.can_execute(ctx) is True


# ── execute — failure path ────────────────────────────────────────────────────


@pytest.mark.unit()
class TestExecuteFailurePath:
    async def test_step_fails_noncritically_when_quote_unavailable(self) -> None:
        collector = _make_collector(quote=None, history=None)
        ctx = _make_context()

        result = await collector.execute(ctx)

        assert result.status == StepStatus.FAILED
        assert "MARKET_DATA_UNAVAILABLE" in result.output_summary
        # Non-critical: market_data not set
        assert ctx.outputs.market_data is None

    async def test_step_name_and_index_in_failure_result(self) -> None:
        collector = _make_collector(quote=None)
        ctx = _make_context()

        result = await collector.execute(ctx)

        assert result.step_name == "MarketDataCollector"
        assert result.step_index == 2


# ── execute — success path ────────────────────────────────────────────────────


@pytest.mark.unit()
class TestExecuteSuccessPath:
    async def test_quote_stored_in_context(self) -> None:
        quote = MarketData(available=True, price=175.0)
        collector = _make_collector(quote=quote, history=None)
        ctx = _make_context()

        result = await collector.execute(ctx)

        assert result.status == StepStatus.COMPLETE
        assert ctx.outputs.market_data is not None
        assert ctx.outputs.market_data.price == 175.0

    async def test_price_history_stored_in_context(self) -> None:
        quote = MarketData(available=True, price=175.0)
        datapoints = _make_datapoints([100.0, 101.0, 102.0, 103.0, 104.0])
        history = PriceHistory(available=True, datapoints=datapoints)
        collector = _make_collector(quote=quote, history=history)
        ctx = _make_context()

        await collector.execute(ctx)

        assert ctx.outputs.price_history is not None
        assert len(ctx.outputs.price_history.datapoints) == 5

    async def test_empty_history_allowed(self) -> None:
        """Step completes successfully even when history is None."""
        quote = MarketData(available=True, price=175.0)
        collector = _make_collector(quote=quote, history=None)
        ctx = _make_context()

        result = await collector.execute(ctx)

        assert result.status == StepStatus.COMPLETE
        assert ctx.outputs.price_history is None


# ── Trend direction ───────────────────────────────────────────────────────────


@pytest.mark.unit()
class TestTrendDirection:
    def test_trend_direction_upward(self) -> None:
        """Strongly rising prices → 'upward'."""
        # Mean ≈ 105, threshold = 0.525; slope = 10 (huge uptrend)
        closes = [100.0 + i * 10 for i in range(10)]
        datapoints = _make_datapoints(closes)
        assert _compute_trend_direction(datapoints) == "upward"

    def test_trend_direction_downward(self) -> None:
        """Strongly falling prices → 'downward'."""
        closes = [200.0 - i * 10 for i in range(10)]
        datapoints = _make_datapoints(closes)
        assert _compute_trend_direction(datapoints) == "downward"

    def test_trend_direction_sideways_within_threshold(self) -> None:
        """Tiny oscillation within ±0.5 % per day → 'sideways'."""
        # Slope ≈ 0, mean = 100 → threshold = 0.5; slope is near-zero
        closes = [100.0, 100.1, 99.9, 100.0, 100.1, 99.9, 100.0, 100.1]
        datapoints = _make_datapoints(closes)
        assert _compute_trend_direction(datapoints) == "sideways"

    def test_trend_direction_uses_last_20_points(self) -> None:
        """Only the last 20 prices are used; earlier extreme values are ignored."""
        # 10 very high prices followed by 20 slowly rising prices
        early_closes = [1000.0] * 10
        recent_closes = [100.0 + i * 0.001 for i in range(20)]  # near-flat upward
        all_closes = early_closes + recent_closes
        datapoints = _make_datapoints(all_closes)
        # The last 20 prices are near 100 with a tiny positive slope
        result = _compute_trend_direction(datapoints)
        # Could be sideways or upward — just ensure it doesn't reflect the spike
        assert result in ("sideways", "upward")

    def test_trend_direction_none_when_insufficient_data(self) -> None:
        datapoints = _make_datapoints([100.0])
        assert _compute_trend_direction(datapoints) is None

    def test_trend_direction_none_when_no_close_prices(self) -> None:
        datapoints = [PricePoint(date="2024-01-01")]
        assert _compute_trend_direction(datapoints) is None


# ── Volatility flag ───────────────────────────────────────────────────────────


@pytest.mark.unit()
class TestVolatilityFlag:
    def test_volatility_flag_above_3_percent(self) -> None:
        """Large daily swings → flag = True."""
        # Alternating ±10 % swings produce a stdev well above 3 %
        closes = [100.0, 110.0, 100.0, 110.0, 100.0, 110.0, 100.0, 110.0]
        datapoints = _make_datapoints(closes)
        assert _compute_volatility_flag(datapoints) is True

    def test_volatility_flag_below_3_percent(self) -> None:
        """Tiny daily moves → flag = False."""
        # 0.1 % daily changes → stdev ≈ 0.001
        closes = [100.0 * (1 + 0.001 * i) for i in range(20)]
        datapoints = _make_datapoints(closes)
        assert _compute_volatility_flag(datapoints) is False

    def test_volatility_flag_false_with_insufficient_data(self) -> None:
        datapoints = _make_datapoints([100.0, 110.0])
        assert _compute_volatility_flag(datapoints) is False

    def test_volatility_flag_false_with_no_data(self) -> None:
        assert _compute_volatility_flag([]) is False


# ── Enrichment integration ────────────────────────────────────────────────────


@pytest.mark.unit()
class TestEnrichment:
    async def test_trend_direction_recomputed_in_step(self) -> None:
        """The step overwrites the provider's trend_direction with regression result."""
        quote = MarketData(available=True, price=175.0)
        # Build a clearly upward trend
        closes = [100.0 + i * 5 for i in range(20)]
        datapoints = _make_datapoints(closes)
        # Provider returns 'flat' (its simple estimate); step must recompute
        history = PriceHistory(available=True, datapoints=datapoints, trend_direction="flat")
        collector = _make_collector(quote=quote, history=history)
        ctx = _make_context()

        await collector.execute(ctx)

        assert ctx.outputs.price_history is not None
        assert ctx.outputs.price_history.trend_direction == "upward"
