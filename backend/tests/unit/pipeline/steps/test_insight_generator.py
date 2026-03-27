"""Unit tests for InsightGenerator pipeline step (T-037)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.domain.models.events import ExtractedEvent
from app.domain.models.insights import InsightSections
from app.domain.models.market import CompanyInfo, MarketData
from app.domain.models.news import ArticleSummary
from app.domain.models.sentiment import SentimentDistribution, SentimentResult
from app.lib.constants import AI_ANALYSIS_DISCLAIMER
from app.pipeline.context import PipelineContext, PipelineOutputs
from app.pipeline.steps.base import StepStatus
from app.pipeline.steps.insight_generator import (
    INSUFFICIENT_DATA_FALLBACK,
    InsightGenerator,
    InsightsLLMOutput,
    _apply_fallback,
)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_context(
    with_market_data: bool = True,
    with_sentiment: bool = True,
    with_articles: bool = True,
    with_events: bool = True,
) -> PipelineContext:
    outputs = PipelineOutputs()
    outputs.company_info = CompanyInfo(ticker="AAPL", name="Apple Inc.")

    if with_market_data:
        outputs.market_data = MarketData(
            available=True,
            price=185.5,
            change_pct=1.2,
            change_abs=2.2,
            volume=54_000_000.0,
            market_cap=2_850_000_000_000.0,
            pe_ratio=28.5,
            week_52_high=198.0,
            week_52_low=143.0,
            currency="USD",
        )

    if with_sentiment:
        outputs.sentiment = SentimentResult(
            available=True,
            distribution=SentimentDistribution(positive=60, neutral=25, negative=15),
            dominant="Predominantly Positive",
            article_count=5,
        )

    if with_articles:
        outputs.article_summaries = [
            ArticleSummary(
                article_id=f"a{i:04d}",
                url=f"https://example.com/{i}",
                title=f"Headline {i}",
                published_at=datetime(2024, 3, i, tzinfo=UTC),
                source_name="Reuters",
                content_snippet="content",
                summary=f"Summary {i}.",
                topics=["Earnings"],
                sentiment="positive",
                sentiment_score=0.9,
                summarization_failed=False,
            )
            for i in range(1, 4)
        ]

    if with_events:
        outputs.events = [
            ExtractedEvent(
                event_type="Earnings Announcement",
                description="Apple beat Q4 earnings.",
                detected_date="2024-03-01",
                source_article_indices=[1],
            )
        ]

    return PipelineContext(
        run_id=uuid4(),
        ticker="AAPL",
        llm_provider=MagicMock(),
        outputs=outputs,
    )


def _full_insights_response() -> str:
    return json.dumps(
        {
            "company_overview": "Apple is a leading tech company.",
            "recent_developments": "Apple beat Q4 earnings.",
            "sentiment_overview": "Sentiment is predominantly positive.",
            "potential_drivers": "Strong iPhone sales.",
            "potential_risks": "Macro headwinds.",
            "ai_summary": "Apple looks solid for the quarter.",
        }
    )


def _make_generator() -> tuple[InsightGenerator, MagicMock]:
    mock_loader = MagicMock()
    mock_loader.render.return_value = "rendered insights prompt"
    generator = InsightGenerator(prompt_loader=mock_loader)
    return generator, mock_loader


# ── Metadata ──────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestMetadata:
    def test_step_metadata(self) -> None:
        gen, _ = _make_generator()
        assert gen.name == "InsightGenerator"
        assert gen.step_index == 8
        assert gen.critical is False
        assert gen.max_retries == 2

    def test_can_execute_always_true(self) -> None:
        gen, _ = _make_generator()
        ctx = _make_context(
            with_market_data=False,
            with_sentiment=False,
            with_articles=False,
            with_events=False,
        )
        ctx.outputs.company_info = None
        assert gen.can_execute(ctx) is True


# ── Successful generation ─────────────────────────────────────────────────────


@pytest.mark.unit
class TestSuccessfulGeneration:
    async def test_insights_generated_with_all_data(self) -> None:
        ctx = _make_context()
        ctx.llm_provider.complete = AsyncMock(return_value=_full_insights_response())

        gen, _ = _make_generator()
        result = await gen.execute(ctx)

        assert result.status == StepStatus.COMPLETE
        assert ctx.outputs.insights is not None
        assert ctx.outputs.insights.company_overview == "Apple is a leading tech company."

    async def test_insight_generated_with_no_market_data(self) -> None:
        """Step executes and produces insights even without market data."""
        ctx = _make_context(with_market_data=False)
        ctx.llm_provider.complete = AsyncMock(return_value=_full_insights_response())

        gen, _ = _make_generator()
        result = await gen.execute(ctx)

        assert result.status == StepStatus.COMPLETE
        assert ctx.outputs.insights is not None

    async def test_insight_generated_with_minimal_data(self) -> None:
        """can_execute=True even with no data at all."""
        ctx = _make_context(
            with_market_data=False,
            with_sentiment=False,
            with_articles=False,
            with_events=False,
        )
        ctx.llm_provider.complete = AsyncMock(return_value=_full_insights_response())

        gen, _ = _make_generator()
        result = await gen.execute(ctx)

        assert result.status == StepStatus.COMPLETE

    async def test_insights_stored_as_insight_sections(self) -> None:
        ctx = _make_context()
        ctx.llm_provider.complete = AsyncMock(return_value=_full_insights_response())

        gen, _ = _make_generator()
        await gen.execute(ctx)

        assert isinstance(ctx.outputs.insights, InsightSections)


# ── Fallback for empty sections ───────────────────────────────────────────────


@pytest.mark.unit
class TestFallback:
    async def test_empty_sections_replaced_with_fallback_string(self) -> None:
        """Empty string sections are replaced with the canonical fallback."""
        ctx = _make_context()
        ctx.llm_provider.complete = AsyncMock(
            return_value=json.dumps(
                {
                    "company_overview": "Apple is big.",
                    "recent_developments": "",  # empty → fallback
                    "sentiment_overview": "   ",  # whitespace → fallback
                    "potential_drivers": "Strong iPhone.",
                    "potential_risks": "",  # empty → fallback
                    "ai_summary": "Solid quarter.",
                }
            )
        )

        gen, _ = _make_generator()
        await gen.execute(ctx)

        insights = ctx.outputs.insights
        assert insights is not None
        assert insights.recent_developments == INSUFFICIENT_DATA_FALLBACK
        assert insights.sentiment_overview == INSUFFICIENT_DATA_FALLBACK
        assert insights.potential_risks == INSUFFICIENT_DATA_FALLBACK
        assert insights.company_overview == "Apple is big."

    def test_apply_fallback_replaces_all_empty_fields(self) -> None:
        output = InsightsLLMOutput(
            company_overview="",
            recent_developments="Something.",
            sentiment_overview="",
            potential_drivers="",
            potential_risks="Risk.",
            ai_summary="",
        )
        result = _apply_fallback(output)
        assert result.company_overview == INSUFFICIENT_DATA_FALLBACK
        assert result.recent_developments == "Something."
        assert result.potential_drivers == INSUFFICIENT_DATA_FALLBACK
        assert result.ai_summary == INSUFFICIENT_DATA_FALLBACK
        assert result.potential_risks == "Risk."

    def test_apply_fallback_whitespace_only_is_fallback(self) -> None:
        output = InsightsLLMOutput(company_overview="   ")
        result = _apply_fallback(output)
        assert result.company_overview == INSUFFICIENT_DATA_FALLBACK


# ── Disclaimer hardcoded ──────────────────────────────────────────────────────


@pytest.mark.unit
class TestDisclaimer:
    def test_disclaimer_is_hardcoded_not_llm_generated(self) -> None:
        """InsightsResult.disclaimer equals AI_ANALYSIS_DISCLAIMER constant."""
        from app.domain.models.insights import InsightsResult

        result = InsightsResult(
            available=True,
            sections=InsightSections(),
        )
        assert result.disclaimer == AI_ANALYSIS_DISCLAIMER

    def test_disclaimer_never_sourced_from_llm(self) -> None:
        """The LLM output schema does not include a 'disclaimer' field."""
        assert not hasattr(InsightsLLMOutput.model_fields, "disclaimer")
        assert "disclaimer" not in InsightsLLMOutput.model_fields


# ── Token budget truncation ───────────────────────────────────────────────────


@pytest.mark.unit
class TestTokenBudget:
    async def test_token_budget_truncates_articles(self) -> None:
        """Articles are removed when prompt exceeds MAX_PROMPT_TOKENS."""
        ctx = _make_context()

        render_call_count = 0

        def mock_render(template: str, **kwargs: object) -> str:
            nonlocal render_call_count
            render_call_count += 1
            articles = kwargs.get("articles", [])
            # Return a long prompt only on the first call (before truncation)
            if render_call_count == 1:
                return "x" * 13000  # > 3000 tokens (each token ~4 chars)
            return "short prompt"

        ctx.llm_provider.complete = AsyncMock(return_value=_full_insights_response())

        gen, mock_loader = _make_generator()
        mock_loader.render.side_effect = mock_render

        await gen.execute(ctx)

        # render was called multiple times (first + truncation iterations)
        assert render_call_count > 1

    async def test_token_budget_removes_articles_before_events(self) -> None:
        """Article truncation occurs before event truncation."""
        ctx = _make_context()

        remaining_articles: list[list] = [[]]
        remaining_events: list[list] = [[]]
        render_call_count = [0]

        def mock_render(template: str, **kwargs: object) -> str:
            render_call_count[0] += 1
            articles = kwargs.get("articles", [])
            events = kwargs.get("events", [])
            remaining_articles[0] = list(articles)  # type: ignore[arg-type]
            remaining_events[0] = list(events)  # type: ignore[arg-type]
            # Force truncation: return long prompt until articles is empty
            if articles:
                return "x" * 13000
            return "short prompt"

        ctx.llm_provider.complete = AsyncMock(return_value=_full_insights_response())

        gen, mock_loader = _make_generator()
        mock_loader.render.side_effect = mock_render

        await gen.execute(ctx)

        # By the time we stop, articles were truncated while events remained
        # (events are only removed if articles alone can't fix the budget)
        # Articles should be empty at the final render
        assert len(remaining_articles[0]) == 0


# ── Retry hint ────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestRetryHint:
    async def test_retry_hint_appended_to_prompt(self) -> None:
        ctx = _make_context()
        ctx.set_llm_retry_hint("InsightGenerator", "MUST RETURN JSON")
        ctx.llm_provider.complete = AsyncMock(return_value=_full_insights_response())

        captured: list[str] = []

        async def capture(prompt: str, **kwargs: object) -> str:
            captured.append(prompt)
            return _full_insights_response()

        ctx.llm_provider.complete = capture

        gen, mock_loader = _make_generator()
        mock_loader.render.return_value = "base prompt"
        await gen.execute(ctx)

        assert len(captured) == 1
        assert "MUST RETURN JSON" in captured[0]
