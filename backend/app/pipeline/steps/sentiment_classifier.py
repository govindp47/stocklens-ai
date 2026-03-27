"""Step 6 — SentimentClassifier (non-critical pipeline step).

Classifies sentiment for every article in article_summaries concurrently using
the same asyncio.gather fan-out pattern as ArticleSummarizer.

Key invariants enforced by this step:
  1. Score clamping: LLM score is clamped to [0.0, 1.0].
  2. Low-confidence override: score < 0.5 forces label to "neutral".
  3. Distribution rounding: positive + neutral + negative == 100 always
     (largest-remainder method).
  4. emerging_concern_flag = True iff negative distribution >= 70%.
  5. limited_data_caveat = True iff article_count < 3.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.exceptions import LLMParseError
from app.domain.models.news import ArticleSummary
from app.domain.models.sentiment import SentimentDistribution, SentimentResult
from app.infrastructure.providers.llm_parser import (
    CORRECTIVE_HINT,
    MAX_PROMPT_TOKENS,
    estimate_tokens,
    extract_json,
)
from app.infrastructure.providers.prompt_loader import PromptLoader
from app.pipeline.context import PipelineContext
from app.pipeline.steps.base import BasePipelineStep, StepResult, StepStatus

logger = logging.getLogger(__name__)

_ALLOWED_SENTIMENTS: frozenset[str] = frozenset({"positive", "neutral", "negative"})


# ── LLM output schema ─────────────────────────────────────────────────────────


class SentimentLLMOutput(BaseModel):
    """Expected JSON schema returned by the LLM for sentiment.j2."""

    model_config = ConfigDict(
        extra="ignore",
        str_strip_whitespace=True,
    )

    sentiment: str = Field(default="neutral")
    score: float = Field(default=0.5)

    @field_validator("sentiment", mode="before")
    @classmethod
    def validate_sentiment(cls, v: Any) -> str:
        """Reject labels outside the allowed vocabulary → default to 'neutral'."""
        if isinstance(v, str) and v.lower() in _ALLOWED_SENTIMENTS:
            return v.lower()
        return "neutral"

    @field_validator("score", mode="before")
    @classmethod
    def validate_score(cls, v: Any) -> float:
        """Coerce to float; clamp to [0.0, 1.0]."""
        try:
            f = float(v)
        except (TypeError, ValueError):
            return 0.5
        return max(0.0, min(1.0, f))


# ── Distribution helpers ──────────────────────────────────────────────────────


def _compute_distribution(sentiments: list[str]) -> dict[str, int]:
    """Compute percentage distribution that sums to exactly 100.

    Uses the largest-remainder (Hamilton) method to fix rounding errors:
      1. Compute exact float percentages.
      2. Take the integer floor of each.
      3. Compute remainder = 100 - sum(floors).
      4. Give the remainder to categories ordered by largest fractional part.

    Args:
        sentiments: A non-empty list of sentiment label strings.

    Returns:
        dict with keys "positive", "neutral", "negative" summing to 100.
    """
    total = len(sentiments)
    counts = {
        "positive": sentiments.count("positive"),
        "neutral": sentiments.count("neutral"),
        "negative": sentiments.count("negative"),
    }

    # Exact float percentages
    floats: dict[str, float] = {k: counts[k] / total * 100 for k in counts}

    # Floor each value
    floors: dict[str, int] = {k: int(floats[k]) for k in floats}

    # Remainder to distribute
    remainder = 100 - sum(floors.values())

    # Sort by fractional part descending; apply remainder to top categories
    fractional_parts = sorted(
        floats.keys(),
        key=lambda k: floats[k] - floors[k],
        reverse=True,
    )
    for i in range(remainder):
        floors[fractional_parts[i % len(fractional_parts)]] += 1

    assert sum(floors.values()) == 100, (
        f"Distribution must sum to 100, got {sum(floors.values())}: {floors}"
    )
    return floors


def _compute_dominant_label(dist: dict[str, int]) -> str:
    """Derive the dominant sentiment label from the percentage distribution.

    Six-condition lookup table (evaluated in order):
      1. positive >= 60%                               → "Predominantly Positive"
      2. positive >= 40% AND negative < 25%            → "Mostly Positive"
      3. negative >= 60%                               → "Predominantly Negative"
      4. negative >= 40% AND positive < 25%            → "Mostly Negative"
      5. abs(positive - negative) <= 15 AND neutral > 40% → "Neutral / No Strong Signal"
      6. default                                       → "Mixed"
    """
    pos = dist["positive"]
    neu = dist["neutral"]
    neg = dist["negative"]

    if pos >= 60:
        return "Predominantly Positive"
    if pos >= 40 and neg < 25:
        return "Mostly Positive"
    if neg >= 60:
        return "Predominantly Negative"
    if neg >= 40 and pos < 25:
        return "Mostly Negative"
    if abs(pos - neg) <= 15 and neu > 40:
        return "Neutral / No Strong Signal"
    return "Mixed"


# ── Step ──────────────────────────────────────────────────────────────────────


class SentimentClassifier(BasePipelineStep):
    """Classify per-article sentiment and aggregate into a SentimentResult.

    Attributes:
        name: Step identifier used in logging, metrics, and persistence.
        step_index: Execution order index (6 = sixth step).
        critical: False — sentiment unavailability is tolerated.
        max_retries: 1 — the orchestrator may retry the step once on exception.
    """

    name: str = "SentimentClassifier"
    step_index: int = 6
    critical: bool = False
    max_retries: int = 1

    def __init__(self, prompt_loader: PromptLoader) -> None:
        self._prompt_loader = prompt_loader

    # ── PipelineStep Protocol ──────────────────────────────────────────────

    def can_execute(self, context: PipelineContext) -> bool:
        """Requires Step 5 (ArticleSummarizer) to have run.

        Zero summaries is still executable — the classifier will produce an
        available=False SentimentResult.
        """
        return context.outputs.article_summaries is not None

    async def execute(self, context: PipelineContext) -> StepResult:
        """Classify sentiment for all article summaries concurrently.

        Uses asyncio.gather(return_exceptions=True) to isolate per-article
        failures.  Articles where classification failed default to "neutral".
        Always returns COMPLETE; sentiment unavailability is encoded in the
        SentimentResult model.
        """
        summaries = context.outputs.article_summaries or []
        start_ms = int(time.monotonic() * 1000)

        company_info = context.outputs.company_info
        company_name: str = (
            (company_info.name or context.ticker)
            if company_info is not None
            else context.ticker
        )

        logger.info(
            "Starting sentiment classification",
            extra={"ticker": context.ticker, "article_count": len(summaries)},
        )

        if not summaries:
            context.outputs.sentiment = SentimentResult(available=False)
            duration_ms = int(time.monotonic() * 1000) - start_ms
            return StepResult(
                step_name=self.name,
                step_index=self.step_index,
                status=StepStatus.COMPLETE,
                duration_ms=duration_ms,
                output_summary="article_count=0 sentiment=unavailable",
            )

        coroutines = [
            self._classify_article(article, context, company_name)
            for article in summaries
        ]

        raw_results: list[Any] = list(
            await asyncio.gather(*coroutines, return_exceptions=True)
        )

        # Collect sentiment labels; exceptions → default to "neutral"
        classified_sentiments: list[str] = []
        updated_summaries: list[ArticleSummary] = []

        for article, result in zip(summaries, raw_results):
            if isinstance(result, BaseException):
                logger.warning(
                    "Sentiment classification raised exception",
                    extra={"article_id": article.article_id, "error": str(result)},
                )
                classified_sentiments.append("neutral")
                updated_summaries.append(article)
            else:
                label, score = result
                classified_sentiments.append(label)
                # Enrich article with sentiment fields
                updated_summaries.append(
                    ArticleSummary(
                        **{
                            k: v
                            for k, v in article.model_dump().items()
                            if k not in ("sentiment", "sentiment_score")
                        },
                        sentiment=label,
                        sentiment_score=score,
                    )
                )

        # Update article_summaries with sentiment-enriched versions
        context.outputs.article_summaries = updated_summaries

        # Aggregate distribution with largest-remainder rounding
        dist = _compute_distribution(classified_sentiments)
        dominant = _compute_dominant_label(dist)
        article_count = len(classified_sentiments)

        sentiment_result = SentimentResult(
            available=True,
            distribution=SentimentDistribution(
                positive=dist["positive"],
                neutral=dist["neutral"],
                negative=dist["negative"],
            ),
            dominant=dominant,
            article_count=article_count,
            limited_data_caveat=article_count < 3,
            emerging_concern_flag=dist["negative"] >= 70,
        )

        context.outputs.sentiment = sentiment_result

        duration_ms = int(time.monotonic() * 1000) - start_ms
        logger.info(
            "Sentiment classification complete",
            extra={
                "dominant": dominant,
                "distribution": dist,
                "article_count": article_count,
                "duration_ms": duration_ms,
            },
        )

        return StepResult(
            step_name=self.name,
            step_index=self.step_index,
            status=StepStatus.COMPLETE,
            duration_ms=duration_ms,
            output_summary=(
                f"dominant={dominant} "
                f"pos={dist['positive']} neu={dist['neutral']} neg={dist['negative']} "
                f"count={article_count}"
            ),
        )

    # ── Per-article helpers ────────────────────────────────────────────────

    async def _classify_article(
        self,
        article: ArticleSummary,
        context: PipelineContext,
        company_name: str,
    ) -> tuple[str, float]:
        """Classify sentiment for a single article with one corrective retry.

        Returns:
            (label, score) where label ∈ {"positive", "neutral", "negative"}
            and score ∈ [0.0, 1.0].

        ExternalProviderError propagates to asyncio.gather (not caught here).
        LLMParseError triggers one corrective retry; second failure returns
        ("neutral", 0.5) to avoid blocking the aggregation step.
        """
        from pydantic import ValidationError

        prompt = self._prompt_loader.render(
            "sentiment.j2",
            ticker=context.ticker,
            company_name=company_name,
            title=article.title,
            summary=article.summary,
        )

        if estimate_tokens(prompt) > MAX_PROMPT_TOKENS:
            logger.warning(
                "Sentiment prompt exceeds token budget",
                extra={"ticker": context.ticker},
            )

        for attempt in range(2):
            current_prompt = prompt if attempt == 0 else prompt + CORRECTIVE_HINT
            try:
                raw = await context.llm_provider.complete(
                    current_prompt,
                    max_tokens=200,
                    temperature=0.1,
                )
                parsed = extract_json(raw)
                output = SentimentLLMOutput.model_validate(parsed)

                # Low-confidence override: score < 0.5 → force neutral
                label = output.sentiment
                score = output.score
                if score < 0.5:
                    label = "neutral"

                return label, score

            except (LLMParseError, ValidationError):
                if attempt == 1:
                    logger.warning(
                        "Sentiment classification failed after corrective retry",
                        extra={"article_id": article.article_id},
                    )
                    return "neutral", 0.5

        # Defensive: unreachable with range(2)
        return "neutral", 0.5
