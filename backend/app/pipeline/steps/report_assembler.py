"""Step 9 — ReportAssembler (CRITICAL pipeline step — no I/O, no LLM calls).

Assembles the AnalysisReport domain object from all context.outputs fields.
Computes completeness, partial_data_notices, data_sources, and content_hash.
Serialises the report to JSON and stores it in context.outputs.final_report_json
so the orchestrator can persist it to the database.

This step is critical=True: if it raises an unhandled exception the orchestrator
marks the run as failed.  In practice it should never fail for external reasons
since it contains no network I/O.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Literal

from app.domain.models.events import EventsResult
from app.domain.models.insights import InsightsResult
from app.domain.models.market import CompanyInfo, MarketData, PriceHistory
from app.domain.models.news import ArticleSummary, NewsCollection
from app.domain.models.report import AnalysisReport, DataSource
from app.domain.models.sentiment import SentimentResult
from app.pipeline.context import PipelineContext
from app.pipeline.steps.base import BasePipelineStep, StepResult, StepStatus

logger = logging.getLogger(__name__)


# ── Completeness computation ──────────────────────────────────────────────────


def _compute_completeness(
    context: PipelineContext,
) -> Literal["complete", "partial", "minimal"]:
    """Derive the completeness level from what pipeline outputs are available.

    Algorithm (from architecture doc § Step 9):
      critical_ok = company_info is not None AND
                    (market_data is not None OR deduplicated_articles is not empty)
      if not critical_ok → "minimal"

      optional = sum of:
        market_data is not None
        deduplicated_articles is not empty
        sentiment is not None
        insights is not None
      if optional >= 3 → "complete"
      else → "partial"
    """
    company_ok = context.outputs.company_info is not None
    market_ok = context.outputs.market_data is not None
    news_ok = bool(context.outputs.deduplicated_articles)

    critical_ok = company_ok and (market_ok or news_ok)
    if not critical_ok:
        return "minimal"

    optional = sum(
        [
            market_ok,
            news_ok,
            context.outputs.sentiment is not None,
            context.outputs.insights is not None,
        ]
    )
    return "complete" if optional >= 3 else "partial"


# ── Partial data notices ──────────────────────────────────────────────────────


def _collect_partial_notices(context: PipelineContext) -> list[str]:
    """Build human-readable notices for each unavailable data section."""
    notices: list[str] = []

    if context.outputs.market_data is None:
        notices.append(
            "Market data is unavailable. The stock overview panel could not be populated."
        )
    if context.outputs.price_history is None:
        notices.append(
            "Price history is unavailable. The price chart could not be displayed."
        )
    if not context.outputs.deduplicated_articles:
        notices.append(
            "No relevant news articles were found for this ticker."
        )
    elif not context.outputs.article_summaries:
        notices.append(
            "Article summarisation was unavailable. Raw headlines are shown."
        )
    if context.outputs.sentiment is None:
        notices.append(
            "Sentiment analysis is unavailable. The sentiment panel could not be populated."
        )
    if context.outputs.events is None:
        notices.append(
            "Event extraction was unavailable. The events panel could not be populated."
        )
    if context.outputs.insights is None:
        notices.append(
            "AI insights are unavailable. The research overview could not be generated."
        )

    return notices


# ── Data sources ──────────────────────────────────────────────────────────────


def _collect_data_sources(context: PipelineContext) -> list[DataSource]:
    """List only providers that successfully contributed data."""
    sources: list[DataSource] = []

    if context.outputs.market_data is not None:
        sources.append(DataSource(name="yfinance", status="ok"))

    if context.outputs.raw_articles:
        sources.append(DataSource(name="yahoo_rss", status="ok"))
    elif context.outputs.raw_articles is not None:
        sources.append(DataSource(name="yahoo_rss", status="unavailable", detail="No articles found"))

    if context.outputs.article_summaries or context.outputs.insights:
        sources.append(
            DataSource(
                name=context.llm_provider.model_name,
                status="ok" if context.outputs.insights is not None else "partial",
            )
        )

    return sources


# ── Step ──────────────────────────────────────────────────────────────────────


class ReportAssembler(BasePipelineStep):
    """Assemble the final AnalysisReport from all pipeline outputs.

    Attributes:
        name: Step identifier used in logging, metrics, and persistence.
        step_index: Execution order index (9 = ninth step).
        critical: True — assembly failure marks the run as failed.
        max_retries: 0 — pure computation; retrying is meaningless.
    """

    name: str = "ReportAssembler"
    step_index: int = 9
    critical: bool = True
    max_retries: int = 0

    # ── PipelineStep Protocol ──────────────────────────────────────────────

    def can_execute(self, context: PipelineContext) -> bool:  # noqa: ARG002
        """Always executable — assembly works with any subset of available data."""
        return True

    async def execute(self, context: PipelineContext) -> StepResult:
        """Assemble AnalysisReport, compute completeness, serialise to JSON.

        Writes context.outputs.final_report_json for the orchestrator to persist.
        """
        start_ms = int(time.monotonic() * 1000)

        logger.info(
            "Assembling analysis report",
            extra={"ticker": context.ticker, "run_id": str(context.run_id)},
        )

        # ── Map None outputs to domain defaults ────────────────────────────

        company = context.outputs.company_info or CompanyInfo(ticker=context.ticker)

        market_data: MarketData = context.outputs.market_data or MarketData(
            available=False
        )

        price_history: PriceHistory = context.outputs.price_history or PriceHistory(
            available=False
        )

        article_summaries: list[ArticleSummary] = context.outputs.article_summaries or []
        news = NewsCollection(
            available=bool(article_summaries),
            articles=article_summaries,
        )

        sentiment: SentimentResult = context.outputs.sentiment or SentimentResult(
            available=False
        )

        events_result = (
            EventsResult(available=True, events=context.outputs.events)
            if context.outputs.events is not None
            else EventsResult(available=False)
        )

        insights_result = (
            InsightsResult(available=True, sections=context.outputs.insights)
            if context.outputs.insights is not None
            else InsightsResult(available=False)
        )

        # ── Compute completeness ───────────────────────────────────────────

        completeness = _compute_completeness(context)

        # ── Collect notices and sources ────────────────────────────────────

        partial_notices = _collect_partial_notices(context)
        data_sources = _collect_data_sources(context)

        # ── Assemble the report ────────────────────────────────────────────

        report = AnalysisReport(
            run_id=context.run_id,
            ticker=context.ticker,
            company=company,
            market_data=market_data,
            price_history=price_history,
            news=news,
            sentiment=sentiment,
            events=events_result,
            insights=insights_result,
            data_sources=data_sources,
            completeness=completeness,
            partial_data_notices=partial_notices,
        )

        # ── Serialise to JSON for DB persistence ──────────────────────────
        # AnalysisReport computes content_hash in its model_validator.

        context.outputs.final_report_json = report.model_dump_json()

        duration_ms = int(time.monotonic() * 1000) - start_ms

        logger.info(
            "Report assembled",
            extra={
                "run_id": str(context.run_id),
                "ticker": context.ticker,
                "completeness": completeness,
                "content_hash": report.content_hash,
                "duration_ms": duration_ms,
            },
        )

        return StepResult(
            step_name=self.name,
            step_index=self.step_index,
            status=StepStatus.COMPLETE,
            duration_ms=duration_ms,
            output_summary=f"completeness={completeness} hash={str(report.content_hash)[:8]}",
        )
