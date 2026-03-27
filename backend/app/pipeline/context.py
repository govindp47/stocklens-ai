"""PipelineContext and PipelineOutputs — the shared mutable aggregate for a pipeline run."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from app.domain.models import (
    ArticleSummary,
    CompanyInfo,
    ExtractedEvent,
    InsightSections,
    MarketData,
    PriceHistory,
    RawArticle,
    SentimentResult,
)
from app.infrastructure.providers import LLMProvider


@dataclass
class PipelineOutputs:
    """Mutable accumulator for all step outputs within a pipeline run.

    Every field defaults to None; steps write into the fields they own.
    Helper predicates allow downstream steps to check prerequisites without
    directly accessing fields (avoids scattered None-checks).
    """

    company_info: CompanyInfo | None = None
    market_data: MarketData | None = None
    price_history: PriceHistory | None = None
    raw_articles: list[RawArticle] | None = None
    deduplicated_articles: list[RawArticle] | None = None
    article_summaries: list[ArticleSummary] | None = None
    sentiment: SentimentResult | None = None
    events: list[ExtractedEvent] | None = None
    insights: InsightSections | None = None

    # ── predicates ────────────────────────────────────────────────────────

    def has_company_info(self) -> bool:
        return self.company_info is not None

    def has_market_data(self) -> bool:
        return self.market_data is not None

    def has_price_history(self) -> bool:
        return self.price_history is not None

    def has_news(self) -> bool:
        return bool(self.raw_articles)

    def has_deduplicated_articles(self) -> bool:
        return bool(self.deduplicated_articles)

    def has_article_summaries(self) -> bool:
        return bool(self.article_summaries)

    def has_sentiment(self) -> bool:
        return self.sentiment is not None

    def has_events(self) -> bool:
        return bool(self.events)

    def has_insights(self) -> bool:
        return self.insights is not None


@dataclass
class PipelineContext:
    """Single mutable aggregate that flows through all pipeline steps.

    Steps communicate exclusively through this object — they read from
    ``outputs`` to satisfy prerequisites and write into ``outputs`` upon
    success.  No step receives data from another step directly.

    ``llm_retry_hints`` carries corrective prompt hints between retry
    attempts of LLM-backed steps; the orchestrator calls
    ``set_llm_retry_hint`` after a parse failure so the next attempt can
    adjust its prompt.
    """

    run_id: UUID
    ticker: str
    llm_provider: LLMProvider  # injected by the orchestrator (T-017)
    outputs: PipelineOutputs = field(default_factory=PipelineOutputs)
    llm_retry_hints: dict[str, str] = field(default_factory=dict)

    # ── LLM retry hint helpers ────────────────────────────────────────────

    def set_llm_retry_hint(self, step_name: str, hint: str) -> None:
        """Store a corrective prompt hint for ``step_name``."""
        self.llm_retry_hints[step_name] = hint

    def get_llm_retry_hint(self, step_name: str) -> str | None:
        """Return the stored hint for ``step_name``, or None if absent."""
        return self.llm_retry_hints.get(step_name)
