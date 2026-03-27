"""Sentiment analysis domain models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator


class SentimentDistribution(BaseModel):
    """Percentage breakdown of article sentiment.

    positive + neutral + negative must equal 100.
    """

    model_config = ConfigDict(frozen=True)

    positive: int = 0
    neutral: int = 0
    negative: int = 0

    @model_validator(mode="after")
    def _check_sums_to_100(self) -> SentimentDistribution:
        total = self.positive + self.neutral + self.negative
        if total != 100:
            raise ValueError(
                f"SentimentDistribution values must sum to 100, got {total} "
                f"(positive={self.positive}, neutral={self.neutral}, negative={self.negative})"
            )
        return self


class SentimentResult(BaseModel):
    """Aggregated sentiment outcome for a full article corpus."""

    model_config = ConfigDict(frozen=True)

    available: bool = False
    distribution: SentimentDistribution | None = None
    dominant: str | None = None  # "positive" | "neutral" | "negative"
    article_count: int = 0
    limited_data_caveat: bool = False
    emerging_concern_flag: bool = False
