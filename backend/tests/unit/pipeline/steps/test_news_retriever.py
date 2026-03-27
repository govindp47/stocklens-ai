"""Unit tests for NewsRetriever pipeline step (T-025)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.domain.exceptions import ExternalProviderError
from app.domain.models.market import CompanyInfo
from app.domain.models.news import RawArticle
from app.pipeline.context import PipelineContext, PipelineOutputs
from app.pipeline.steps.base import StepStatus
from app.pipeline.steps.news_retriever import NewsRetriever


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_context(
    with_company_info: bool = True,
    ticker: str = "AAPL",
    company_name: str = "Apple Inc.",
) -> PipelineContext:
    outputs = PipelineOutputs()
    if with_company_info:
        outputs.company_info = CompanyInfo(ticker=ticker, name=company_name)
    return PipelineContext(
        run_id=uuid4(),
        ticker=ticker,
        llm_provider=MagicMock(),
        outputs=outputs,
    )


def _make_retriever(
    articles: list[RawArticle] | None = None,
    raise_error: ExternalProviderError | None = None,
) -> NewsRetriever:
    mock_provider = MagicMock()
    if raise_error is not None:
        mock_provider.get_articles = AsyncMock(side_effect=raise_error)
    else:
        mock_provider.get_articles = AsyncMock(return_value=articles or [])
    return NewsRetriever(news_provider=mock_provider)


def _make_article(n: int = 1) -> RawArticle:
    return RawArticle(
        article_id=f"abc{n:013d}",
        url=f"https://example.com/article/{n}",
        title=f"Test article {n}",
        published_at=datetime(2024, 1, n, tzinfo=UTC),
        source_name="TestSource",
    )


# ── Metadata ──────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestMetadata:
    def test_step_metadata(self) -> None:
        retriever = _make_retriever()
        assert retriever.name == "NewsRetriever"
        assert retriever.step_index == 3
        assert retriever.critical is False
        assert retriever.max_retries == 2


# ── can_execute ───────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestCanExecute:
    def test_can_execute_requires_company_info(self) -> None:
        retriever = _make_retriever()
        ctx = _make_context(with_company_info=False)
        assert retriever.can_execute(ctx) is False

    def test_can_execute_true_with_company_info(self) -> None:
        retriever = _make_retriever()
        ctx = _make_context(with_company_info=True)
        assert retriever.can_execute(ctx) is True


# ── Zero articles is COMPLETE ─────────────────────────────────────────────────


@pytest.mark.unit
class TestZeroArticles:
    async def test_zero_articles_is_complete_not_failed(self) -> None:
        """get_articles returning [] must produce COMPLETE, not FAILED."""
        retriever = _make_retriever(articles=[])
        ctx = _make_context()

        result = await retriever.execute(ctx)

        assert result.status == StepStatus.COMPLETE

    async def test_zero_articles_sets_empty_list_not_none(self) -> None:
        """context.outputs.raw_articles must be [] not None after zero results."""
        retriever = _make_retriever(articles=[])
        ctx = _make_context()

        await retriever.execute(ctx)

        assert ctx.outputs.raw_articles is not None
        assert ctx.outputs.raw_articles == []

    async def test_zero_articles_count_in_summary(self) -> None:
        retriever = _make_retriever(articles=[])
        ctx = _make_context()

        result = await retriever.execute(ctx)

        assert "article_count=0" in result.output_summary


# ── Articles stored ───────────────────────────────────────────────────────────


@pytest.mark.unit
class TestArticlesStored:
    async def test_articles_stored_in_context(self) -> None:
        articles = [_make_article(1), _make_article(2), _make_article(3)]
        retriever = _make_retriever(articles=articles)
        ctx = _make_context()

        result = await retriever.execute(ctx)

        assert result.status == StepStatus.COMPLETE
        assert ctx.outputs.raw_articles is not None
        assert len(ctx.outputs.raw_articles) == 3

    async def test_article_count_in_output_summary(self) -> None:
        articles = [_make_article(i) for i in range(1, 6)]
        retriever = _make_retriever(articles=articles)
        ctx = _make_context()

        result = await retriever.execute(ctx)

        assert "article_count=5" in result.output_summary

    async def test_provider_called_with_correct_args(self) -> None:
        mock_provider = MagicMock()
        mock_provider.get_articles = AsyncMock(return_value=[])
        retriever = NewsRetriever(news_provider=mock_provider)
        ctx = _make_context(ticker="MSFT", company_name="Microsoft Corp.")

        await retriever.execute(ctx)

        mock_provider.get_articles.assert_called_once_with("MSFT", "Microsoft Corp.")


# ── Provider error → FAILED ───────────────────────────────────────────────────


@pytest.mark.unit
class TestProviderError:
    async def test_step_fails_on_provider_error(self) -> None:
        error = ExternalProviderError(
            "RSS feed unreachable",
            error_code="RSS_FEED_ERROR",
            user_message="News feed temporarily unavailable.",
            is_retryable=True,
        )
        retriever = _make_retriever(raise_error=error)
        ctx = _make_context()

        result = await retriever.execute(ctx)

        assert result.status == StepStatus.FAILED

    async def test_provider_error_code_in_summary(self) -> None:
        error = ExternalProviderError(
            "Connection refused",
            error_code="RSS_CONNECTION_ERROR",
            user_message="Connection refused.",
            is_retryable=False,
        )
        retriever = _make_retriever(raise_error=error)
        ctx = _make_context()

        result = await retriever.execute(ctx)

        assert "RSS_CONNECTION_ERROR" in result.output_summary

    async def test_raw_articles_not_set_on_provider_error(self) -> None:
        """raw_articles must remain None when the provider call fails."""
        error = ExternalProviderError(
            "Timeout",
            error_code="RSS_TIMEOUT",
            user_message="Timed out.",
            is_retryable=True,
        )
        retriever = _make_retriever(raise_error=error)
        ctx = _make_context()

        await retriever.execute(ctx)

        assert ctx.outputs.raw_articles is None

    async def test_step_name_and_index_in_failure_result(self) -> None:
        error = ExternalProviderError(
            "err",
            error_code="ERR",
            user_message="err",
        )
        retriever = _make_retriever(raise_error=error)
        ctx = _make_context()

        result = await retriever.execute(ctx)

        assert result.step_name == "NewsRetriever"
        assert result.step_index == 3


# ── Fallback when company_name is None ───────────────────────────────────────


@pytest.mark.unit
class TestCompanyNameFallback:
    async def test_ticker_used_as_company_name_when_name_is_none(self) -> None:
        """If CompanyInfo.name is None the ticker is used as the company name."""
        mock_provider = MagicMock()
        mock_provider.get_articles = AsyncMock(return_value=[])
        retriever = NewsRetriever(news_provider=mock_provider)

        outputs = PipelineOutputs()
        outputs.company_info = CompanyInfo(ticker="GOOG", name=None)
        ctx = PipelineContext(
            run_id=uuid4(),
            ticker="GOOG",
            llm_provider=MagicMock(),
            outputs=outputs,
        )

        await retriever.execute(ctx)

        # company_name falls back to ticker "GOOG" when name is None
        mock_provider.get_articles.assert_called_once_with("GOOG", "GOOG")
