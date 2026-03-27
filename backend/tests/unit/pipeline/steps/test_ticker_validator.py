"""Unit tests for TickerValidator pipeline step."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.domain.exceptions import ExternalProviderError, TickerNotResolvableError
from app.domain.models.market import CompanyInfo, MarketData
from app.pipeline.context import PipelineContext, PipelineOutputs
from app.pipeline.steps.base import StepStatus
from app.pipeline.steps.ticker_validator import TickerValidator


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_validator(
    cache_resolve: bool | None = None,
    is_resolvable: bool = True,
    quote: MarketData | None = None,
    company_info: CompanyInfo | None = None,
) -> tuple[TickerValidator, MagicMock, MagicMock]:
    """Return a (TickerValidator, mock_repo, mock_provider) triple."""
    mock_repo = MagicMock()
    mock_repo.resolve = AsyncMock(return_value=cache_resolve)
    mock_repo.set_resolved = AsyncMock()

    mock_provider = MagicMock()
    mock_provider.is_ticker_resolvable = AsyncMock(return_value=is_resolvable)
    mock_provider.get_quote = AsyncMock(return_value=quote)
    mock_provider.get_company_info = AsyncMock(
        return_value=company_info
        or CompanyInfo(ticker="AAPL", name="Apple Inc.", exchange="NASDAQ")
    )

    validator = TickerValidator(
        ticker_cache_repo=mock_repo,
        market_data_provider=mock_provider,
    )
    return validator, mock_repo, mock_provider


def _make_context(ticker: str = "AAPL") -> PipelineContext:
    return PipelineContext(
        run_id=uuid4(),
        ticker=ticker,
        llm_provider=MagicMock(),
        outputs=PipelineOutputs(),
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestTickerValidatorMetadata:
    def test_step_metadata(self) -> None:
        validator, _, _ = _make_validator()
        assert validator.name == "TickerValidator"
        assert validator.step_index == 1
        assert validator.critical is True
        assert validator.max_retries == 2

    def test_can_execute_always_true(self) -> None:
        validator, _, _ = _make_validator()
        ctx = _make_context()
        assert validator.can_execute(ctx) is True


@pytest.mark.unit
class TestNegativeCache:
    async def test_negative_cache_skips_external_call(self) -> None:
        """A cached False result must raise immediately without any provider call."""
        validator, mock_repo, mock_provider = _make_validator(cache_resolve=False)
        ctx = _make_context()

        with pytest.raises(TickerNotResolvableError):
            await validator.execute(ctx)

        mock_provider.is_ticker_resolvable.assert_not_called()
        mock_provider.get_quote.assert_not_called()

    async def test_negative_cache_does_not_write_cache(self) -> None:
        """No set_resolved call when negative cache hits."""
        validator, mock_repo, _ = _make_validator(cache_resolve=False)
        ctx = _make_context()

        with pytest.raises(TickerNotResolvableError):
            await validator.execute(ctx)

        mock_repo.set_resolved.assert_not_called()


@pytest.mark.unit
class TestCacheMissFlow:
    async def test_unresolvable_ticker_raises_error(self) -> None:
        """Cache miss + provider returns False → raise TickerNotResolvableError."""
        validator, mock_repo, mock_provider = _make_validator(
            cache_resolve=None, is_resolvable=False
        )
        ctx = _make_context(ticker="FAKE")

        with pytest.raises(TickerNotResolvableError):
            await validator.execute(ctx)

        mock_provider.is_ticker_resolvable.assert_called_once_with("FAKE")

    async def test_unresolvable_ticker_writes_negative_cache(self) -> None:
        validator, mock_repo, _ = _make_validator(
            cache_resolve=None, is_resolvable=False
        )
        ctx = _make_context(ticker="FAKE")

        with pytest.raises(TickerNotResolvableError):
            await validator.execute(ctx)

        mock_repo.set_resolved.assert_called_once_with("FAKE", is_resolvable=False)

    async def test_resolvable_ticker_populates_company_info(self) -> None:
        """Cache miss + provider returns True → context.outputs.company_info set."""
        expected_info = CompanyInfo(
            ticker="AAPL", name="Apple Inc.", exchange="NASDAQ"
        )
        validator, _, _ = _make_validator(
            cache_resolve=None,
            is_resolvable=True,
            company_info=expected_info,
        )
        ctx = _make_context()

        result = await validator.execute(ctx)

        assert result.status == StepStatus.COMPLETE
        assert ctx.outputs.company_info is not None
        assert ctx.outputs.company_info.name == "Apple Inc."
        assert ctx.outputs.company_info.ticker == "AAPL"

    async def test_cache_set_after_successful_resolution(self) -> None:
        """set_resolved(is_resolvable=True) is called after successful resolution."""
        validator, mock_repo, _ = _make_validator(cache_resolve=None, is_resolvable=True)
        ctx = _make_context()

        await validator.execute(ctx)

        mock_repo.set_resolved.assert_called_once()
        call_kwargs = mock_repo.set_resolved.call_args
        assert call_kwargs.kwargs.get("is_resolvable") is True or (
            len(call_kwargs.args) >= 2 and call_kwargs.args[1] is True
        )


@pytest.mark.unit
class TestPositiveCacheFlow:
    async def test_positive_cache_skips_is_resolvable_call(self) -> None:
        """Cached True result skips is_ticker_resolvable — only get_company_info called."""
        validator, _, mock_provider = _make_validator(cache_resolve=True)
        ctx = _make_context()

        result = await validator.execute(ctx)

        assert result.status == StepStatus.COMPLETE
        mock_provider.is_ticker_resolvable.assert_not_called()


@pytest.mark.unit
class TestErrorPropagation:
    async def test_external_provider_error_propagates(self) -> None:
        """ExternalProviderError from is_ticker_resolvable propagates for retry."""
        validator, _, mock_provider = _make_validator(cache_resolve=None)
        mock_provider.is_ticker_resolvable = AsyncMock(
            side_effect=ExternalProviderError(
                "Timeout",
                error_code="YFINANCE_TIMEOUT",
                user_message="Timeout",
                is_retryable=True,
            )
        )
        ctx = _make_context()

        with pytest.raises(ExternalProviderError):
            await validator.execute(ctx)

    async def test_ticker_not_resolvable_is_not_retryable_by_nature(self) -> None:
        """TickerNotResolvableError is a distinct exception class."""
        validator, _, _ = _make_validator(cache_resolve=None, is_resolvable=False)
        ctx = _make_context(ticker="FAKE")

        with pytest.raises(TickerNotResolvableError) as exc_info:
            await validator.execute(ctx)

        # TickerNotResolvableError does not carry is_retryable; it is a distinct
        # non-provider error that the orchestrator treats as a hard stop.
        assert exc_info.type is TickerNotResolvableError


@pytest.mark.unit
class TestOutputIntegrity:
    async def test_market_data_populated_when_quote_available(self) -> None:
        """If get_quote returns data, market_data is also set on context.outputs."""
        quote = MarketData(available=True, price=175.0)
        validator, _, _ = _make_validator(
            cache_resolve=None, is_resolvable=True, quote=quote
        )
        ctx = _make_context()

        await validator.execute(ctx)

        assert ctx.outputs.market_data is not None
        assert ctx.outputs.market_data.price == 175.0

    async def test_market_data_not_set_when_quote_none(self) -> None:
        """If get_quote returns None, market_data is not set."""
        validator, _, _ = _make_validator(
            cache_resolve=None, is_resolvable=True, quote=None
        )
        ctx = _make_context()

        await validator.execute(ctx)

        assert ctx.outputs.market_data is None
