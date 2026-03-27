"""Pipeline step registry and factory.

build_step_registry() instantiates all nine pipeline steps with their
dependencies injected from app.state, returning them in step_index order.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.pipeline.steps.article_summarizer import ArticleSummarizer
from app.pipeline.steps.event_extractor import EventExtractor
from app.pipeline.steps.insight_generator import InsightGenerator
from app.pipeline.steps.market_data_collector import MarketDataCollector
from app.pipeline.steps.news_deduplicator import NewsDeduplicator
from app.pipeline.steps.news_retriever import NewsRetriever
from app.pipeline.steps.report_assembler import ReportAssembler
from app.pipeline.steps.sentiment_classifier import SentimentClassifier
from app.pipeline.steps.ticker_validator import TickerValidator

if TYPE_CHECKING:
    from app.pipeline.steps.base import PipelineStep


def build_step_registry(app_state: Any) -> list["PipelineStep"]:
    """Instantiate all nine pipeline steps with injected dependencies.

    Args:
        app_state: The FastAPI ``app.state`` object populated during lifespan
            startup.  Must have the following attributes:
              - market_data_provider  (YFinanceMarketDataProvider)
              - news_feed_provider    (RSSNewsFeedProvider)
              - ticker_cache_repo     (TickerCacheRepository)
              - prompt_loader         (PromptLoader)

    Returns:
        list[PipelineStep] ordered by step_index (1 → 9).
    """
    steps: list[PipelineStep] = [
        # Step 1 — TickerValidator (critical)
        TickerValidator(
            ticker_cache_repo=app_state.ticker_cache_repo,
            market_data_provider=app_state.market_data_provider,
        ),
        # Step 2 — MarketDataCollector (non-critical)
        MarketDataCollector(
            market_data_provider=app_state.market_data_provider,
        ),
        # Step 3 — NewsRetriever (non-critical)
        NewsRetriever(
            news_provider=app_state.news_feed_provider,
        ),
        # Step 4 — NewsDeduplicator (non-critical)
        NewsDeduplicator(),
        # Step 5 — ArticleSummarizer (non-critical)
        ArticleSummarizer(
            prompt_loader=app_state.prompt_loader,
        ),
        # Step 6 — SentimentClassifier (non-critical)
        SentimentClassifier(
            prompt_loader=app_state.prompt_loader,
        ),
        # Step 7 — EventExtractor (non-critical)
        EventExtractor(
            prompt_loader=app_state.prompt_loader,
        ),
        # Step 8 — InsightGenerator (non-critical)
        InsightGenerator(
            prompt_loader=app_state.prompt_loader,
        ),
        # Step 9 — ReportAssembler (CRITICAL)
        ReportAssembler(),
    ]

    # Verify ordering is correct (defensive)
    for i, step in enumerate(steps, start=1):
        assert step.step_index == i, (
            f"Step order mismatch: expected step_index={i}, got {step.step_index} "
            f"for {step.name}"
        )

    return steps
