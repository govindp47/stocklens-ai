"""Unit tests for SentimentClassifier pipeline step (T-035)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.domain.exceptions import ExternalProviderError
from app.domain.models.market import CompanyInfo
from app.domain.models.news import ArticleSummary
from app.pipeline.context import PipelineContext, PipelineOutputs
from app.pipeline.steps.base import StepStatus
from app.pipeline.steps.sentiment_classifier import (
    SentimentClassifier,
    _compute_distribution,
    _compute_dominant_label,
)

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_summary(n: int = 1, sentiment: str = "") -> ArticleSummary:
    return ArticleSummary(
        article_id=f"article{n:04d}",
        url=f"https://example.com/{n}",
        title=f"Headline {n}",
        published_at=datetime(2024, 3, 1, tzinfo=UTC),
        source_name="Reuters",
        content_snippet="snippet",
        summary=f"Summary of article {n}.",
        topics=["Earnings"],
        sentiment=sentiment,
        sentiment_score=0.0,
        summarization_failed=False,
    )


def _make_context(
    summaries: list[ArticleSummary] | None = None,
    ticker: str = "AAPL",
) -> PipelineContext:
    outputs = PipelineOutputs()
    outputs.company_info = CompanyInfo(ticker=ticker, name="Apple Inc.")
    outputs.article_summaries = summaries
    return PipelineContext(
        run_id=uuid4(),
        ticker=ticker,
        llm_provider=MagicMock(),
        outputs=outputs,
    )


def _sentiment_response(label: str = "positive", score: float = 0.9) -> str:
    return json.dumps({"sentiment": label, "score": score})


def _make_classifier() -> tuple[SentimentClassifier, MagicMock]:
    mock_loader = MagicMock()
    mock_loader.render.return_value = "rendered sentiment prompt"
    classifier = SentimentClassifier(prompt_loader=mock_loader)
    return classifier, mock_loader


# ── Metadata ──────────────────────────────────────────────────────────────────


@pytest.mark.unit()
class TestMetadata:
    def test_step_metadata(self) -> None:
        classifier, _ = _make_classifier()
        assert classifier.name == "SentimentClassifier"
        assert classifier.step_index == 6
        assert classifier.critical is False
        assert classifier.max_retries == 1


# ── can_execute ───────────────────────────────────────────────────────────────


@pytest.mark.unit()
class TestCanExecute:
    def test_can_execute_false_when_summaries_none(self) -> None:
        classifier, _ = _make_classifier()
        ctx = _make_context(summaries=None)
        assert classifier.can_execute(ctx) is False

    def test_can_execute_true_with_empty_list(self) -> None:
        """Zero summaries is executable — produces available=False result."""
        classifier, _ = _make_classifier()
        ctx = _make_context(summaries=[])
        assert classifier.can_execute(ctx) is True

    def test_can_execute_true_with_summaries(self) -> None:
        classifier, _ = _make_classifier()
        ctx = _make_context(summaries=[_make_summary(1)])
        assert classifier.can_execute(ctx) is True


# ── _compute_distribution ─────────────────────────────────────────────────────


@pytest.mark.unit()
class TestComputeDistribution:
    def test_aggregate_distribution_sums_to_100(self) -> None:
        """Core invariant: distribution always sums to exactly 100."""
        dist = _compute_distribution(["positive"] * 3 + ["neutral"] * 4 + ["negative"] * 3)
        assert sum(dist.values()) == 100

    def test_all_positive_gives_100_0_0(self) -> None:
        dist = _compute_distribution(["positive"] * 5)
        assert dist == {"positive": 100, "neutral": 0, "negative": 0}

    def test_all_neutral_gives_0_100_0(self) -> None:
        dist = _compute_distribution(["neutral"] * 5)
        assert dist == {"positive": 0, "neutral": 100, "negative": 0}

    def test_all_negative_gives_0_0_100(self) -> None:
        dist = _compute_distribution(["negative"] * 7)
        assert dist == {"positive": 0, "neutral": 0, "negative": 100}

    def test_single_article_sums_to_100(self) -> None:
        dist = _compute_distribution(["positive"])
        assert sum(dist.values()) == 100

    @pytest.mark.parametrize("n", range(1, 21))
    def test_distribution_sums_to_100_for_all_counts(self, n: int) -> None:
        """Property test: all splits up to n=20 sum to exactly 100."""
        for pos in range(n + 1):
            for neg in range(n - pos + 1):
                neu = n - pos - neg
                sentiments = ["positive"] * pos + ["neutral"] * neu + ["negative"] * neg
                dist = _compute_distribution(sentiments)
                assert (
                    sum(dist.values()) == 100
                ), f"Failed for n={n} pos={pos} neu={neu} neg={neg}: {dist}"


# ── _compute_dominant_label ───────────────────────────────────────────────────


@pytest.mark.unit()
class TestComputeDominantLabel:
    def test_dominant_predominantly_positive(self) -> None:
        assert (
            _compute_dominant_label({"positive": 65, "neutral": 20, "negative": 15})
            == "Predominantly Positive"
        )

    def test_dominant_mostly_positive(self) -> None:
        assert (
            _compute_dominant_label({"positive": 45, "neutral": 35, "negative": 20})
            == "Mostly Positive"
        )

    def test_dominant_predominantly_negative(self) -> None:
        assert (
            _compute_dominant_label({"positive": 10, "neutral": 25, "negative": 65})
            == "Predominantly Negative"
        )

    def test_dominant_mostly_negative(self) -> None:
        assert (
            _compute_dominant_label({"positive": 20, "neutral": 35, "negative": 45})
            == "Mostly Negative"
        )

    def test_dominant_neutral_no_strong_signal(self) -> None:
        # abs(30 - 25) = 5 <= 15, neutral = 45 > 40
        assert (
            _compute_dominant_label({"positive": 30, "neutral": 45, "negative": 25})
            == "Neutral / No Strong Signal"
        )

    def test_dominant_mixed(self) -> None:
        # Doesn't fit any of the first 5 conditions
        assert _compute_dominant_label({"positive": 38, "neutral": 25, "negative": 37}) == "Mixed"

    def test_predominantly_positive_boundary(self) -> None:
        """Exactly 60% positive → Predominantly Positive."""
        assert (
            _compute_dominant_label({"positive": 60, "neutral": 20, "negative": 20})
            == "Predominantly Positive"
        )

    def test_mostly_positive_boundary(self) -> None:
        """Exactly 40% positive, 24% negative → Mostly Positive."""
        assert (
            _compute_dominant_label({"positive": 40, "neutral": 36, "negative": 24})
            == "Mostly Positive"
        )


# ── Score clamping and low-confidence override ────────────────────────────────


@pytest.mark.unit()
class TestScoreHandling:
    async def test_low_confidence_reclassified_to_neutral(self) -> None:
        """score < 0.5 overrides label to 'neutral' regardless of LLM output."""
        summaries = [_make_summary(1)]
        ctx = _make_context(summaries=summaries)
        ctx.llm_provider.complete = AsyncMock(
            return_value=_sentiment_response("positive", score=0.4)
        )

        classifier, _ = _make_classifier()
        await classifier.execute(ctx)

        updated = ctx.outputs.article_summaries
        assert updated is not None
        assert updated[0].sentiment == "neutral"

    async def test_score_clamping_above_1(self) -> None:
        """score > 1.0 is clamped to 1.0."""
        summaries = [_make_summary(1)]
        ctx = _make_context(summaries=summaries)
        ctx.llm_provider.complete = AsyncMock(
            return_value=json.dumps({"sentiment": "positive", "score": 1.8})
        )

        classifier, _ = _make_classifier()
        await classifier.execute(ctx)

        updated = ctx.outputs.article_summaries
        assert updated is not None
        assert updated[0].sentiment_score == 1.0

    async def test_score_clamping_below_0(self) -> None:
        """score < 0.0 is clamped to 0.0, which is < 0.5 → neutral."""
        summaries = [_make_summary(1)]
        ctx = _make_context(summaries=summaries)
        ctx.llm_provider.complete = AsyncMock(
            return_value=json.dumps({"sentiment": "negative", "score": -0.5})
        )

        classifier, _ = _make_classifier()
        await classifier.execute(ctx)

        updated = ctx.outputs.article_summaries
        assert updated is not None
        assert updated[0].sentiment_score == 0.0
        assert updated[0].sentiment == "neutral"  # clamped to 0.0 < 0.5


# ── Aggregate flags ───────────────────────────────────────────────────────────


@pytest.mark.unit()
class TestAggregateFlags:
    async def test_limited_data_caveat_when_fewer_than_3(self) -> None:
        """limited_data_caveat=True when article_count < 3."""
        summaries = [_make_summary(1), _make_summary(2)]  # 2 articles
        ctx = _make_context(summaries=summaries)
        ctx.llm_provider.complete = AsyncMock(return_value=_sentiment_response("positive", 0.8))

        classifier, _ = _make_classifier()
        await classifier.execute(ctx)

        assert ctx.outputs.sentiment is not None
        assert ctx.outputs.sentiment.limited_data_caveat is True

    async def test_no_limited_data_caveat_when_3_or_more(self) -> None:
        summaries = [_make_summary(i) for i in range(1, 4)]
        ctx = _make_context(summaries=summaries)
        ctx.llm_provider.complete = AsyncMock(return_value=_sentiment_response("positive", 0.8))

        classifier, _ = _make_classifier()
        await classifier.execute(ctx)

        assert ctx.outputs.sentiment is not None
        assert ctx.outputs.sentiment.limited_data_caveat is False

    async def test_emerging_concern_flag_at_70_percent(self) -> None:
        """emerging_concern_flag=True iff negative distribution >= 70%."""
        # 7 negative out of 10 = 70%
        summaries = [_make_summary(i) for i in range(1, 11)]
        ctx = _make_context(summaries=summaries)

        call_count = 0

        async def side_effect(*args: object, **kwargs: object) -> str:
            nonlocal call_count
            call_count += 1
            label = "negative" if call_count <= 7 else "positive"
            return _sentiment_response(label, 0.9)

        ctx.llm_provider.complete = side_effect

        classifier, _ = _make_classifier()
        await classifier.execute(ctx)

        assert ctx.outputs.sentiment is not None
        dist = ctx.outputs.sentiment.distribution
        assert dist is not None
        assert dist.negative >= 70
        assert ctx.outputs.sentiment.emerging_concern_flag is True

    async def test_emerging_concern_flag_not_set_below_70(self) -> None:
        """emerging_concern_flag=False when negative < 70%."""
        summaries = [_make_summary(i) for i in range(1, 4)]
        ctx = _make_context(summaries=summaries)
        ctx.llm_provider.complete = AsyncMock(return_value=_sentiment_response("negative", 0.9))

        # 3/3 = 100% negative → flag should be True; let's use 2 negative, 1 positive
        summaries2 = [_make_summary(1), _make_summary(2), _make_summary(3)]
        ctx2 = _make_context(summaries=summaries2)

        call_count2 = 0

        async def side_effect2(*args: object, **kwargs: object) -> str:
            nonlocal call_count2
            call_count2 += 1
            # 2 negative, 1 positive → 67% negative < 70%
            label = "negative" if call_count2 <= 2 else "positive"
            return _sentiment_response(label, 0.9)

        ctx2.llm_provider.complete = side_effect2

        classifier2, _ = _make_classifier()
        await classifier2.execute(ctx2)

        assert ctx2.outputs.sentiment is not None
        assert ctx2.outputs.sentiment.emerging_concern_flag is False


# ── Step-level LLM failure ────────────────────────────────────────────────────


@pytest.mark.unit()
class TestLLMFailure:
    async def test_step_fails_noncritically_when_llm_unavailable(self) -> None:
        """When all articles fail classification, step still returns COMPLETE."""
        summaries = [_make_summary(1), _make_summary(2)]
        ctx = _make_context(summaries=summaries)
        ctx.llm_provider.complete = AsyncMock(
            side_effect=ExternalProviderError(
                "LLM down",
                error_code="OLLAMA_CONNECTION_ERROR",
                user_message="Cannot reach Ollama.",
                is_retryable=True,
            )
        )

        classifier, _ = _make_classifier()
        result = await classifier.execute(ctx)

        assert result.status == StepStatus.COMPLETE
        # All articles fail → all default to "neutral"
        assert ctx.outputs.sentiment is not None
        assert ctx.outputs.sentiment.available is True
        assert ctx.outputs.sentiment.dominant is not None

    async def test_empty_summaries_returns_unavailable(self) -> None:
        """Zero articles → SentimentResult(available=False)."""
        ctx = _make_context(summaries=[])

        classifier, _ = _make_classifier()
        result = await classifier.execute(ctx)

        assert result.status == StepStatus.COMPLETE
        assert ctx.outputs.sentiment is not None
        assert ctx.outputs.sentiment.available is False


# ── Distribution sums to 100 in full flow ─────────────────────────────────────


@pytest.mark.unit()
class TestDistributionInvariant:
    async def test_distribution_sums_to_100(self) -> None:
        """End-to-end: SentimentDistribution model validator confirms sum == 100."""
        summaries = [_make_summary(i) for i in range(1, 8)]  # 7 articles
        ctx = _make_context(summaries=summaries)

        call_count = 0

        async def side_effect(*args: object, **kwargs: object) -> str:
            nonlocal call_count
            call_count += 1
            # 3 positive, 2 neutral, 2 negative
            if call_count <= 3:
                return _sentiment_response("positive", 0.8)
            if call_count <= 5:
                return _sentiment_response("neutral", 0.8)
            return _sentiment_response("negative", 0.8)

        ctx.llm_provider.complete = side_effect

        classifier, _ = _make_classifier()
        await classifier.execute(ctx)

        assert ctx.outputs.sentiment is not None
        dist = ctx.outputs.sentiment.distribution
        assert dist is not None
        assert dist.positive + dist.neutral + dist.negative == 100
