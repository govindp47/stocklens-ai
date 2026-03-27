"""AnalysisReport — the canonical output model of the StockLens AI pipeline.

This is the top-level domain object that is persisted to analysis_runs.report_data
as JSONB and served by the GET /api/v1/results/{run_id} endpoint.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.models.events import EventsResult
from app.domain.models.insights import InsightsResult
from app.domain.models.market import CompanyInfo, MarketData, PriceHistory
from app.domain.models.news import NewsCollection
from app.domain.models.sentiment import SentimentResult
from app.lib.constants import SCHEMA_VERSION


class DataSource(BaseModel):
    """Records which external data provider contributed to this report."""

    model_config = ConfigDict(frozen=True)

    name: str  # e.g. "yfinance", "yahoo_rss", "ollama"
    status: str  # "ok" | "partial" | "unavailable"
    detail: str = ""


class AnalysisReport(BaseModel):
    """Immutable, fully-assembled output of one pipeline execution.

    Fields:
        ticker: Normalised uppercase ticker symbol (e.g. "AAPL").
        company: Resolved company metadata.
        market_data: Current price quote and key ratios.
        price_history: 3-month OHLCV series.
        news: Processed and summarised article collection.
        sentiment: Aggregated sentiment distribution and dominant label.
        events: Business events extracted from the article corpus.
        insights: LLM-generated six-section analysis overview.
        data_sources: Which external providers were used and their status.
        schema_version: Version of this model schema for forward-compatibility.
        completeness: Pipeline-level completeness indicator.
        partial_data_notices: Human-readable notices about unavailable sections.
        error_notices: Non-fatal errors surfaced for debugging.
        content_hash: SHA-256 of the report JSON for cache key generation.
        generated_at: UTC timestamp when the report was assembled.
    """

    model_config = ConfigDict(frozen=True)

    run_id: UUID
    ticker: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)

    company: CompanyInfo
    market_data: MarketData = Field(default_factory=MarketData)
    price_history: PriceHistory = Field(default_factory=PriceHistory)
    news: NewsCollection = Field(default_factory=NewsCollection)
    sentiment: SentimentResult = Field(default_factory=SentimentResult)
    events: EventsResult = Field(default_factory=EventsResult)
    insights: InsightsResult = Field(default_factory=InsightsResult)

    data_sources: list[DataSource] = Field(default_factory=list)
    schema_version: str = SCHEMA_VERSION

    completeness: Literal["complete", "partial", "minimal"] = "minimal"
    partial_data_notices: list[str] = Field(default_factory=list)
    error_notices: list[str] = Field(default_factory=list)

    content_hash: str | None = None

    @model_validator(mode="after")
    def _compute_content_hash(self) -> AnalysisReport:
        """Compute a deterministic SHA-256 hash of the report body.

        Uses model_dump with mode='json' to serialise UUIDs and datetimes
        consistently before hashing. The hash itself is excluded from hashing.
        """
        if self.content_hash is None:
            payload = self.model_dump(mode="json", exclude={"content_hash"})
            serialised = json.dumps(payload, sort_keys=True, default=str)
            digest = hashlib.sha256(serialised.encode()).hexdigest()
            # Pydantic frozen models disallow attribute assignment;
            # use model_copy(update=...) to return a new instance with the hash.
            # However, model_validator(mode="after") must return self directly —
            # we use object.__setattr__ since frozen enforcement happens post-init.
            object.__setattr__(self, "content_hash", digest)
        return self
