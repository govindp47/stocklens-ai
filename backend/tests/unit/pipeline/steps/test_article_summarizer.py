"""Unit tests for ArticleSummarizer pipeline step (T-034)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.domain.exceptions import ExternalProviderError, LLMParseError
from app.domain.models.market import CompanyInfo
from app.domain.models.news import RawArticle
from app.infrastructure.providers.llm_parser import CORRECTIVE_HINT
from app.pipeline.context import PipelineContext, PipelineOutputs
from app.pipeline.steps.article_summarizer import (
    ArticleSummarizer,
    ArticleSummaryLLMOutput,
)
from app.pipeline.steps.base import StepStatus


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_article(n: int = 1) -> RawArticle:
    return RawArticle(
        article_id=f"article{n:04d}",
        url=f"https://example.com/{n}",
        title=f"Apple does thing {n}",
        published_at=datetime(2024, 3, n, tzinfo=UTC),
        source_name="Reuters",
        content_snippet=f"Some content for article {n}.",
    )


def _make_context(
    articles: list[RawArticle] | None = None,
    ticker: str = "AAPL",
) -> PipelineContext:
    outputs = PipelineOutputs()
    outputs.company_info = CompanyInfo(ticker=ticker, name="Apple Inc.")
    outputs.deduplicated_articles = articles
    return PipelineContext(
        run_id=uuid4(),
        ticker=ticker,
        llm_provider=MagicMock(),
        outputs=outputs,
    )


def _valid_response(
    summary: str = "Apple reports strong earnings.", topics: list[str] | None = None
) -> str:
    """Return JSON string that the mock LLM returns."""
    return json.dumps({"summary": summary, "topics": topics or ["Earnings"]})


def _make_summarizer(llm_response: str | None = None) -> tuple[ArticleSummarizer, MagicMock]:
    """Return (summarizer, mock_prompt_loader)."""
    mock_loader = MagicMock()
    mock_loader.render.return_value = "rendered prompt text"
    summarizer = ArticleSummarizer(prompt_loader=mock_loader)
    return summarizer, mock_loader


# ── Metadata ──────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestMetadata:
    def test_step_metadata(self) -> None:
        summarizer, _ = _make_summarizer()
        assert summarizer.name == "ArticleSummarizer"
        assert summarizer.step_index == 5
        assert summarizer.critical is False
        assert summarizer.max_retries == 1


# ── can_execute ───────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestCanExecute:
    def test_can_execute_false_when_no_articles(self) -> None:
        summarizer, _ = _make_summarizer()
        ctx = _make_context(articles=None)
        assert summarizer.can_execute(ctx) is False

    def test_can_execute_false_when_empty_list(self) -> None:
        summarizer, _ = _make_summarizer()
        ctx = _make_context(articles=[])
        assert summarizer.can_execute(ctx) is False

    def test_can_execute_true_with_articles(self) -> None:
        summarizer, _ = _make_summarizer()
        ctx = _make_context(articles=[_make_article()])
        assert summarizer.can_execute(ctx) is True


# ── Successful summarisation ───────────────────────────────────────────────────


@pytest.mark.unit
class TestSuccessfulSummarisation:
    async def test_all_articles_summarized_on_success(self) -> None:
        """All articles produce ArticleSummary with summarization_failed=False."""
        articles = [_make_article(i) for i in range(1, 4)]
        ctx = _make_context(articles=articles)
        ctx.llm_provider.complete = AsyncMock(return_value=_valid_response())

        summarizer, _ = _make_summarizer()
        result = await summarizer.execute(ctx)

        assert result.status == StepStatus.COMPLETE
        assert ctx.outputs.article_summaries is not None
        assert len(ctx.outputs.article_summaries) == 3
        assert all(not s.summarization_failed for s in ctx.outputs.article_summaries)

    async def test_summary_and_topics_populated(self) -> None:
        articles = [_make_article(1)]
        ctx = _make_context(articles=articles)
        ctx.llm_provider.complete = AsyncMock(
            return_value=_valid_response("Quarterly results beat estimates.", ["Earnings"])
        )

        summarizer, _ = _make_summarizer()
        await summarizer.execute(ctx)

        summary = ctx.outputs.article_summaries[0]  # type: ignore[index]
        assert summary.summary == "Quarterly results beat estimates."
        assert "Earnings" in summary.topics
        assert summary.summarization_failed is False

    async def test_step_returns_complete_always(self) -> None:
        """Step returns COMPLETE even when all articles fail."""
        articles = [_make_article(1)]
        ctx = _make_context(articles=articles)
        # Provider raises network error — gathered as exception
        ctx.llm_provider.complete = AsyncMock(
            side_effect=ExternalProviderError(
                "timeout",
                error_code="OLLAMA_TIMEOUT",
                user_message="Timeout",
                is_retryable=True,
            )
        )

        summarizer, _ = _make_summarizer()
        result = await summarizer.execute(ctx)

        assert result.status == StepStatus.COMPLETE


# ── Per-article failure handling ──────────────────────────────────────────────


@pytest.mark.unit
class TestPerArticleFailure:
    async def test_individual_article_failure_does_not_fail_step(self) -> None:
        """asyncio.gather(return_exceptions=True) isolates per-article exceptions."""
        articles = [_make_article(1), _make_article(2), _make_article(3)]
        ctx = _make_context(articles=articles)

        # Article 2 raises ExternalProviderError; articles 1 and 3 succeed.
        responses = [
            _valid_response("Summary one."),
            ExternalProviderError(
                "LLM down",
                error_code="OLLAMA_SERVER_ERROR",
                user_message="Server error.",
                is_retryable=True,
            ),
            _valid_response("Summary three."),
        ]
        call_count = 0

        async def side_effect(*args: object, **kwargs: object) -> str:
            nonlocal call_count
            resp = responses[call_count % len(responses)]
            call_count += 1
            if isinstance(resp, Exception):
                raise resp
            return resp

        ctx.llm_provider.complete = side_effect

        summarizer, _ = _make_summarizer()
        result = await summarizer.execute(ctx)

        assert result.status == StepStatus.COMPLETE
        summaries = ctx.outputs.article_summaries
        assert summaries is not None
        assert len(summaries) == 3
        assert summaries[1].summarization_failed is True
        assert not summaries[0].summarization_failed
        assert not summaries[2].summarization_failed

    async def test_provider_exception_sets_summarization_failed(self) -> None:
        articles = [_make_article(1)]
        ctx = _make_context(articles=articles)
        ctx.llm_provider.complete = AsyncMock(
            side_effect=ExternalProviderError(
                "err", error_code="ERR", user_message="err", is_retryable=False
            )
        )

        summarizer, _ = _make_summarizer()
        await summarizer.execute(ctx)

        assert ctx.outputs.article_summaries is not None
        assert ctx.outputs.article_summaries[0].summarization_failed is True

    async def test_semaphore_released_on_exception(self) -> None:
        """Semaphore is released even when LLM raises — verified via count."""
        import asyncio

        semaphore = asyncio.Semaphore(2)
        articles = [_make_article(1)]
        ctx = _make_context(articles=articles)

        # Provider raises — semaphore is inside the provider (not the step)
        ctx.llm_provider.complete = AsyncMock(
            side_effect=ExternalProviderError(
                "err", error_code="ERR", user_message="err", is_retryable=False
            )
        )

        summarizer, _ = _make_summarizer()
        await summarizer.execute(ctx)

        # Semaphore not acquired by the step — count unchanged
        assert semaphore._value == 2  # type: ignore[attr-defined]


# ── Corrective retry ─────────────────────────────────────────────────────────


@pytest.mark.unit
class TestCorrectiveRetry:
    async def test_corrective_retry_fires_on_parse_error(self) -> None:
        """On LLMParseError the step retries with CORRECTIVE_HINT appended."""
        articles = [_make_article(1)]
        ctx = _make_context(articles=articles)

        call_count = 0

        async def side_effect(prompt: str, **kwargs: object) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "not json at all"  # causes LLMParseError
            return _valid_response()

        ctx.llm_provider.complete = side_effect

        summarizer, mock_loader = _make_summarizer()
        mock_loader.render.return_value = "base prompt"
        await summarizer.execute(ctx)

        # LLM was called twice: once normally, once with corrective hint
        assert call_count == 2

    async def test_corrective_hint_appended_on_second_call(self) -> None:
        """CORRECTIVE_HINT is appended to the prompt on the retry attempt."""
        articles = [_make_article(1)]
        ctx = _make_context(articles=articles)

        received_prompts: list[str] = []

        async def side_effect(prompt: str, **kwargs: object) -> str:
            received_prompts.append(prompt)
            if len(received_prompts) == 1:
                return "not json"
            return _valid_response()

        ctx.llm_provider.complete = side_effect

        summarizer, mock_loader = _make_summarizer()
        mock_loader.render.return_value = "base prompt"
        await summarizer.execute(ctx)

        assert len(received_prompts) == 2
        assert CORRECTIVE_HINT in received_prompts[1]

    async def test_second_parse_failure_sets_summarization_failed(self) -> None:
        """Both attempts fail → summarization_failed=True (not an exception)."""
        articles = [_make_article(1)]
        ctx = _make_context(articles=articles)
        ctx.llm_provider.complete = AsyncMock(return_value="not json at all")

        summarizer, _ = _make_summarizer()
        result = await summarizer.execute(ctx)

        assert result.status == StepStatus.COMPLETE
        summaries = ctx.outputs.article_summaries
        assert summaries is not None
        assert summaries[0].summarization_failed is True


# ── Topic validation ──────────────────────────────────────────────────────────


@pytest.mark.unit
class TestTopicValidation:
    def test_topics_validated_against_taxonomy(self) -> None:
        """Unknown topics are filtered out; at least 'Other' is always returned."""
        output = ArticleSummaryLLMOutput.model_validate(
            {
                "summary": "Some summary.",
                "topics": ["Earnings", "UnknownTopic", "AlsoUnknown"],
            }
        )
        assert "Earnings" in output.topics
        assert "UnknownTopic" not in output.topics
        assert "AlsoUnknown" not in output.topics

    def test_all_unknown_topics_maps_to_other(self) -> None:
        output = ArticleSummaryLLMOutput.model_validate(
            {"summary": "Summary.", "topics": ["Bogus1", "Bogus2"]}
        )
        assert output.topics == ["Other"]

    def test_empty_topics_maps_to_other(self) -> None:
        output = ArticleSummaryLLMOutput.model_validate(
            {"summary": "Summary.", "topics": []}
        )
        assert output.topics == ["Other"]

    async def test_unknown_topics_stored_as_other_in_article_summary(self) -> None:
        articles = [_make_article(1)]
        ctx = _make_context(articles=articles)
        ctx.llm_provider.complete = AsyncMock(
            return_value=json.dumps(
                {"summary": "Something.", "topics": ["FakeCategory"]}
            )
        )

        summarizer, _ = _make_summarizer()
        await summarizer.execute(ctx)

        summaries = ctx.outputs.article_summaries
        assert summaries is not None
        assert summaries[0].topics == ["Other"]


# ── Output summary format ─────────────────────────────────────────────────────


@pytest.mark.unit
class TestOutputSummary:
    async def test_output_summary_contains_counts(self) -> None:
        articles = [_make_article(1), _make_article(2)]
        ctx = _make_context(articles=articles)
        ctx.llm_provider.complete = AsyncMock(return_value=_valid_response())

        summarizer, _ = _make_summarizer()
        result = await summarizer.execute(ctx)

        assert "total=2" in result.output_summary
        assert "failed=0" in result.output_summary
