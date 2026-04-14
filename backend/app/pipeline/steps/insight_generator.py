"""Step 8 — InsightGenerator (non-critical pipeline step).

Synthesises all available pipeline context into a six-section structured
research overview using a single conditional LLM call.

Key behaviours:
  - Runs regardless of which prior steps succeeded (can_execute always True).
  - Uses only the data sections that are available; marks absent sections with
    availability flags so the Jinja2 template renders appropriate fallbacks.
  - Token budget: if the rendered prompt exceeds MAX_PROMPT_TOKENS, articles
    are removed first, then events, until it fits.
  - Empty/missing LLM output sections are replaced with the canonical
    INSUFFICIENT_DATA_FALLBACK string.
  - Disclaimer is the hardcoded AI_ANALYSIS_DISCLAIMER constant — never
    sourced from LLM output.

Retry behaviour is orchestrator-managed (max_retries=2).
"""

from __future__ import annotations

import logging
import time
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.domain.exceptions import LLMParseError
from app.domain.models.events import ExtractedEvent
from app.domain.models.insights import InsightSections
from app.domain.models.news import ArticleSummary
from app.domain.models.sentiment import SentimentResult
from app.infrastructure.providers.llm_parser import (
    MAX_PROMPT_TOKENS,
    estimate_tokens,
    extract_json,
)
from app.infrastructure.providers.prompt_loader import PromptLoader
from app.pipeline.context import PipelineContext
from app.pipeline.steps.base import BasePipelineStep, StepResult, StepStatus

logger = logging.getLogger(__name__)

INSUFFICIENT_DATA_FALLBACK: str = "Insufficient data available for this section"

_MAX_ARTICLES_IN_PROMPT: int = 5
_MAX_EVENTS_IN_PROMPT: int = 5


# ── LLM output schema ─────────────────────────────────────────────────────────


class InsightsLLMOutput(BaseModel):
    """Expected JSON schema for the insights.j2 template response."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    company_overview: str = ""
    recent_developments: str = ""
    sentiment_overview: str = ""
    potential_drivers: str = ""
    potential_risks: str = ""
    ai_summary: str = ""


# ── Helpers ───────────────────────────────────────────────────────────────────


def _apply_fallback(output: InsightsLLMOutput) -> InsightsLLMOutput:
    """Replace any empty section string with INSUFFICIENT_DATA_FALLBACK.

    Returns a new InsightsLLMOutput instance (models are not frozen but this
    ensures immutability intent).
    """

    def fix(s: str) -> str:
        return s.strip() if s.strip() else INSUFFICIENT_DATA_FALLBACK

    return InsightsLLMOutput(
        company_overview=fix(output.company_overview),
        recent_developments=fix(output.recent_developments),
        sentiment_overview=fix(output.sentiment_overview),
        potential_drivers=fix(output.potential_drivers),
        potential_risks=fix(output.potential_risks),
        ai_summary=fix(output.ai_summary),
    )


def _render_prompt(
    prompt_loader: PromptLoader,
    ticker: str,
    company_name: str,
    market_data_available: bool,
    market_data: Any,
    sentiment_available: bool,
    sentiment: SentimentResult | None,
    articles: list[ArticleSummary],
    events: list[ExtractedEvent],
) -> str:
    """Render the insights.j2 template with the given context."""
    return prompt_loader.render(
        "insights.j2",
        ticker=ticker,
        company_name=company_name,
        market_data_available=market_data_available,
        market_data=market_data,
        sentiment_available=sentiment_available,
        sentiment=sentiment,
        articles=articles,
        events=events,
    )


# ── Step ──────────────────────────────────────────────────────────────────────


class InsightGenerator(BasePipelineStep):
    """Synthesise a six-section research overview via a single LLM call.

    Attributes:
        name: Step identifier used in logging, metrics, and persistence.
        step_index: Execution order index (8 = eighth step).
        critical: False — insight failure is tolerated; report is partial.
        max_retries: 2 — orchestrator retries on LLMParseError.
    """

    name: str = "InsightGenerator"
    step_index: int = 8
    critical: bool = False
    max_retries: int = 2

    def __init__(self, prompt_loader: PromptLoader) -> None:
        self._prompt_loader = prompt_loader

    # ── PipelineStep Protocol ──────────────────────────────────────────────

    def can_execute(self, context: PipelineContext) -> bool:
        """Always executable — insights can be generated with any subset of data."""
        return True

    async def execute(self, context: PipelineContext) -> StepResult:
        """Build the conditional prompt and call the LLM once for insights.

        Uses only data sections that are marked available in context.outputs.
        Applies the INSUFFICIENT_DATA_FALLBACK to any empty section.
        Sets context.outputs.insights (InsightSections) on success.
        """
        start_ms = int(time.monotonic() * 1000)

        company_info = context.outputs.company_info
        company_name: str = (
            (company_info.name or context.ticker) if company_info is not None else context.ticker
        )

        market_data = context.outputs.market_data
        market_data_available = (
            market_data is not None and market_data.available and market_data.change_pct is not None
        )

        sentiment = context.outputs.sentiment
        sentiment_available = (
            sentiment is not None and sentiment.available and sentiment.distribution is not None
        )

        # Top N most recent articles (sort by published_at descending)
        raw_summaries: list[ArticleSummary] = list(context.outputs.article_summaries or [])
        raw_summaries.sort(key=lambda a: a.published_at, reverse=True)
        articles: list[ArticleSummary] = raw_summaries[:_MAX_ARTICLES_IN_PROMPT]

        # Top N events
        events: list[ExtractedEvent] = list(context.outputs.events or [])[:_MAX_EVENTS_IN_PROMPT]

        # Build prompt; apply token-budget truncation (articles first, then events)
        prompt = _render_prompt(
            self._prompt_loader,
            ticker=context.ticker,
            company_name=company_name,
            market_data_available=market_data_available,
            market_data=market_data,
            sentiment_available=sentiment_available,
            sentiment=sentiment,
            articles=articles,
            events=events,
        )

        # Trim articles first to fit within token budget
        while estimate_tokens(prompt) > MAX_PROMPT_TOKENS and articles:
            articles = articles[:-1]
            prompt = _render_prompt(
                self._prompt_loader,
                ticker=context.ticker,
                company_name=company_name,
                market_data_available=market_data_available,
                market_data=market_data,
                sentiment_available=sentiment_available,
                sentiment=sentiment,
                articles=articles,
                events=events,
            )

        # Trim events if still over budget
        while estimate_tokens(prompt) > MAX_PROMPT_TOKENS and events:
            events = events[:-1]
            prompt = _render_prompt(
                self._prompt_loader,
                ticker=context.ticker,
                company_name=company_name,
                market_data_available=market_data_available,
                market_data=market_data,
                sentiment_available=sentiment_available,
                sentiment=sentiment,
                articles=articles,
                events=events,
            )

        if estimate_tokens(prompt) > MAX_PROMPT_TOKENS:
            logger.warning(
                "Insights prompt still exceeds token budget after truncation",
                extra={"ticker": context.ticker, "estimated_tokens": estimate_tokens(prompt)},
            )

        # Append orchestrator-level retry hint if present
        retry_hint = context.get_llm_retry_hint(self.name)
        if retry_hint:
            prompt += f"\n\n{retry_hint}"

        logger.info(
            "Generating insights",
            extra={
                "ticker": context.ticker,
                "market_data_available": market_data_available,
                "sentiment_available": sentiment_available,
                "article_count": len(articles),
                "event_count": len(events),
            },
        )

        raw = await context.llm_provider.complete(
            prompt,
            max_tokens=1500,
            temperature=0.1,
        )

        # extract_json raises LLMParseError on failure → orchestrator retries
        parsed = extract_json(raw)

        try:
            llm_output = InsightsLLMOutput.model_validate(parsed)
        except Exception as exc:
            raise LLMParseError(
                f"InsightGenerator: failed to validate insights schema: {exc}",
                step_name=self.name,
                raw_output=raw,
            ) from exc

        # Replace empty sections with the canonical fallback string
        llm_output = _apply_fallback(llm_output)

        context.outputs.insights = InsightSections(
            company_overview=llm_output.company_overview,
            recent_developments=llm_output.recent_developments,
            sentiment_overview=llm_output.sentiment_overview,
            potential_drivers=llm_output.potential_drivers,
            potential_risks=llm_output.potential_risks,
            ai_summary=llm_output.ai_summary,
        )

        duration_ms = int(time.monotonic() * 1000) - start_ms

        logger.info(
            "Insights generation complete",
            extra={"ticker": context.ticker, "duration_ms": duration_ms},
        )

        summary = f"sections=6 market={market_data_available} sentiment={sentiment_available}"
        return StepResult(
            step_name=self.name,
            step_index=self.step_index,
            status=StepStatus.COMPLETE,
            duration_ms=duration_ms,
            output_summary=summary,
        )
