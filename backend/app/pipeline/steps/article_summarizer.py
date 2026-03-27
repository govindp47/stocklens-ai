"""Step 5 — ArticleSummarizer (non-critical pipeline step).

Calls the LLM once per article concurrently using asyncio.gather.
Per-article failures set summarization_failed=True on the ArticleSummary
without failing the overall step.  The shared semaphore is held inside
LLMProvider.complete() — this step never acquires it directly.

Retry logic (per-article, internal):
  Attempt 1: render summarize.j2, call LLM, extract_json, Pydantic-validate.
  Attempt 2: append CORRECTIVE_HINT to prompt, retry.
  Still failing: return ArticleSummary(summarization_failed=True).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.exceptions import LLMParseError
from app.domain.models.news import ArticleSummary, RawArticle
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

# Allowed topic taxonomy — unknowns map to "Other".
_ALLOWED_TOPICS: frozenset[str] = frozenset(
    {
        "Earnings",
        "Acquisitions",
        "Regulatory",
        "Product Launch",
        "Leadership Change",
        "Market Movement",
        "Other",
    }
)


# ── LLM output schema ─────────────────────────────────────────────────────────


class ArticleSummaryLLMOutput(BaseModel):
    """Expected JSON schema returned by the LLM for summarize.j2.

    Pydantic validates and coerces the raw dict extracted by extract_json().
    Extra fields from the LLM are silently ignored.  Unknown topics are
    replaced with "Other" by the field validator.
    """

    model_config = ConfigDict(
        extra="ignore",
        str_strip_whitespace=True,
    )

    summary: str = Field(min_length=1, max_length=500)
    topics: list[str] = Field(default_factory=list)

    @field_validator("topics", mode="before")
    @classmethod
    def validate_topics(cls, v: Any) -> list[str]:
        """Filter topics against the allowed taxonomy; unknowns map to 'Other'."""
        if not isinstance(v, list):
            return ["Other"]
        filtered = [t for t in v if isinstance(t, str) and t in _ALLOWED_TOPICS]
        return filtered if filtered else ["Other"]


# ── Step ──────────────────────────────────────────────────────────────────────


class ArticleSummarizer(BasePipelineStep):
    """Summarise every deduplicated article via a concurrent LLM fan-out.

    Attributes:
        name: Step identifier used in logging, metrics, and persistence.
        step_index: Execution order index (5 = fifth step).
        critical: False — partial or total summarisation failure is tolerated.
        max_retries: 1 — the orchestrator may retry the entire step once on
            a step-level exception.  Per-article retries are handled internally.
    """

    name: str = "ArticleSummarizer"
    step_index: int = 5
    critical: bool = False
    max_retries: int = 1

    def __init__(self, prompt_loader: PromptLoader) -> None:
        self._prompt_loader = prompt_loader

    # ── PipelineStep Protocol ──────────────────────────────────────────────

    def can_execute(self, context: PipelineContext) -> bool:
        """Requires Step 4 (NewsDeduplicator) to have produced ≥1 article."""
        return (
            context.outputs.deduplicated_articles is not None
            and len(context.outputs.deduplicated_articles) > 0
        )

    async def execute(self, context: PipelineContext) -> StepResult:
        """Fan-out LLM calls across all deduplicated articles concurrently.

        Uses asyncio.gather(return_exceptions=True) so individual article
        failures do not abort the batch.  The step always returns COMPLETE
        even if every article failed summarisation.

        Output: context.outputs.article_summaries (list[ArticleSummary],
                with summarization_failed=True on per-article failures).
        """
        articles = context.outputs.deduplicated_articles or []
        start_ms = int(time.monotonic() * 1000)

        company_info = context.outputs.company_info
        company_name: str = (
            (company_info.name or context.ticker)
            if company_info is not None
            else context.ticker
        )

        logger.info(
            "Starting article summarisation",
            extra={"ticker": context.ticker, "article_count": len(articles)},
        )

        coroutines = [
            self._summarize_article(article, context, company_name)
            for article in articles
        ]

        raw_results: list[Any] = list(
            await asyncio.gather(*coroutines, return_exceptions=True)
        )

        summaries: list[ArticleSummary] = []
        for article, result in zip(articles, raw_results):
            if isinstance(result, BaseException):
                logger.warning(
                    "Article summarisation raised exception",
                    extra={
                        "article_id": article.article_id,
                        "error": str(result),
                    },
                )
                summaries.append(
                    ArticleSummary(**article.model_dump(), summarization_failed=True)
                )
            else:
                summaries.append(result)

        context.outputs.article_summaries = summaries

        duration_ms = int(time.monotonic() * 1000) - start_ms
        failed_count = sum(1 for s in summaries if s.summarization_failed)

        logger.info(
            "Article summarisation complete",
            extra={
                "total": len(summaries),
                "failed": failed_count,
                "duration_ms": duration_ms,
            },
        )

        return StepResult(
            step_name=self.name,
            step_index=self.step_index,
            status=StepStatus.COMPLETE,
            duration_ms=duration_ms,
            output_summary=f"total={len(summaries)} failed={failed_count}",
        )

    # ── Per-article helpers ────────────────────────────────────────────────

    async def _summarize_article(
        self,
        article: RawArticle,
        context: PipelineContext,
        company_name: str,
    ) -> ArticleSummary:
        """Summarise a single article with one internal corrective retry.

        Attempt 1: render prompt, call LLM, extract JSON, validate schema.
        Attempt 2 (only on LLMParseError or ValidationError): append
            CORRECTIVE_HINT and retry exactly once.
        After two failures: return ArticleSummary(summarization_failed=True).

        ExternalProviderError (network/5xx) is NOT caught here — it propagates
        to asyncio.gather where it is handled as a per-article exception.
        """
        from pydantic import ValidationError

        prompt = self._prompt_loader.render(
            "summarize.j2",
            ticker=context.ticker,
            company_name=company_name,
            title=article.title,
            content=article.content_snippet,
        )

        if estimate_tokens(prompt) > MAX_PROMPT_TOKENS:
            logger.warning(
                "Prompt exceeds token budget",
                extra={
                    "ticker": context.ticker,
                    "estimated_tokens": estimate_tokens(prompt),
                },
            )

        for attempt in range(2):
            current_prompt = prompt if attempt == 0 else prompt + CORRECTIVE_HINT
            try:
                raw = await context.llm_provider.complete(
                    current_prompt,
                    max_tokens=500,
                    temperature=0.1,
                )
                parsed = extract_json(raw)
                output = ArticleSummaryLLMOutput.model_validate(parsed)
                return ArticleSummary(
                    **article.model_dump(),
                    summary=output.summary,
                    topics=output.topics,
                )
            except (LLMParseError, ValidationError):
                if attempt == 1:
                    logger.warning(
                        "Article summarisation failed after corrective retry",
                        extra={"article_id": article.article_id},
                    )
                    return ArticleSummary(
                        **article.model_dump(), summarization_failed=True
                    )

        # Defensive: loop exits without return only if range(2) is empty.
        return ArticleSummary(**article.model_dump(), summarization_failed=True)
