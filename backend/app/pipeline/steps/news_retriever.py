"""Step 3 — NewsRetriever (non-critical pipeline step).

Retrieves RSS news articles for the current ticker via RSSNewsFeedProvider.
Zero articles is a valid COMPLETE outcome — absence of news should not block
sentiment analysis or insight generation from market data alone.

Only raises to the orchestrator on unexpected errors; ExternalProviderError
is caught and returned as StepResult(FAILED) so retries are handled uniformly.
"""

from __future__ import annotations

import logging
import time

from app.domain.exceptions import ExternalProviderError
from app.infrastructure.providers.news_feed import RSSNewsFeedProvider
from app.pipeline.context import PipelineContext
from app.pipeline.steps.base import BasePipelineStep, StepResult, StepStatus

logger = logging.getLogger(__name__)


class NewsRetriever(BasePipelineStep):
    """Fetch and store raw RSS articles as the third pipeline step.

    Attributes:
        name: Step identifier used in logging, metrics, and persistence.
        step_index: Execution order index (3 = third step).
        critical: False — missing news is tolerated; market data alone is usable.
        max_retries: 2 — transient network/feed errors are retried by orchestrator.
    """

    name: str = "NewsRetriever"
    step_index: int = 3
    critical: bool = False
    max_retries: int = 2

    def __init__(self, news_provider: RSSNewsFeedProvider) -> None:
        self._news_provider = news_provider

    # ──────────────────────────────────────────────────────────────────────
    # PipelineStep Protocol
    # ──────────────────────────────────────────────────────────────────────

    def can_execute(self, context: PipelineContext) -> bool:
        """Requires Step 1 (TickerValidator) to have populated company_info."""
        return context.outputs.has_company_info()

    async def execute(self, context: PipelineContext) -> StepResult:
        """Fetch articles and populate context.outputs.raw_articles.

        Outcomes:
        - Provider returns a list (even empty) → StepResult(COMPLETE).
          context.outputs.raw_articles is set to the list (never left as None).
        - ExternalProviderError → StepResult(FAILED); pipeline continues.

        Note: An empty article list is a valid COMPLETE outcome; downstream
        steps check ``context.outputs.has_news()`` before consuming articles.
        """
        ticker = context.ticker
        company_info = context.outputs.company_info
        company_name: str = company_info.name or ticker if company_info is not None else ticker
        start_ms = int(time.monotonic() * 1000)

        logger.info(
            "Retrieving news articles",
            extra={"ticker": ticker, "company": company_name},
        )

        try:
            articles = await self._news_provider.get_articles(ticker, company_name)
        except ExternalProviderError as exc:
            duration_ms = int(time.monotonic() * 1000) - start_ms
            logger.warning(
                "News retrieval failed",
                extra={"ticker": ticker, "error_code": exc.error_code},
            )
            return StepResult(
                step_name=self.name,
                step_index=self.step_index,
                status=StepStatus.FAILED,
                duration_ms=duration_ms,
                output_summary=f"{exc.error_code}: {exc.user_message}",
            )

        # Always set raw_articles — empty list is valid (not None)
        context.outputs.raw_articles = articles

        duration_ms = int(time.monotonic() * 1000) - start_ms
        article_count = len(articles)
        logger.info(
            "News articles retrieved",
            extra={
                "ticker": ticker,
                "article_count": article_count,
                "duration_ms": duration_ms,
            },
        )
        return StepResult(
            step_name=self.name,
            step_index=self.step_index,
            status=StepStatus.COMPLETE,
            duration_ms=duration_ms,
            output_summary=f"article_count={article_count}",
        )
