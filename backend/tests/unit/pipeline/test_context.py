"""Unit tests for PipelineContext and PipelineOutputs."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.pipeline.context import PipelineContext, PipelineOutputs


# ──────────────────────────────────────────────────────────────────────────────
# PipelineOutputs
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_outputs_all_none_by_default() -> None:
    outputs = PipelineOutputs()

    assert outputs.company_info is None
    assert outputs.market_data is None
    assert outputs.price_history is None
    assert outputs.raw_articles is None
    assert outputs.deduplicated_articles is None
    assert outputs.article_summaries is None
    assert outputs.sentiment is None
    assert outputs.events is None
    assert outputs.insights is None


@pytest.mark.unit
def test_outputs_has_predicates_return_false_by_default() -> None:
    outputs = PipelineOutputs()

    assert not outputs.has_company_info()
    assert not outputs.has_market_data()
    assert not outputs.has_price_history()
    assert not outputs.has_news()
    assert not outputs.has_deduplicated_articles()
    assert not outputs.has_article_summaries()
    assert not outputs.has_sentiment()
    assert not outputs.has_events()
    assert not outputs.has_insights()


@pytest.mark.unit
def test_outputs_has_market_data_returns_true_when_set() -> None:
    outputs = PipelineOutputs()
    outputs.market_data = MagicMock()  # any non-None value

    assert outputs.has_market_data()


@pytest.mark.unit
def test_outputs_has_news_returns_false_for_empty_list() -> None:
    """has_news() must return False for both None and empty list."""
    outputs = PipelineOutputs()

    outputs.raw_articles = None
    assert not outputs.has_news()

    outputs.raw_articles = []
    assert not outputs.has_news()

    outputs.raw_articles = [MagicMock()]
    assert outputs.has_news()


# ──────────────────────────────────────────────────────────────────────────────
# PipelineContext — LLM retry hints
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_llm_retry_hint_roundtrip() -> None:
    context = PipelineContext(
        run_id=uuid4(),
        ticker="AAPL",
        llm_provider=MagicMock(),
    )

    assert context.get_llm_retry_hint("ArticleSummarizer") is None

    context.set_llm_retry_hint("ArticleSummarizer", "Use valid JSON only.")
    assert context.get_llm_retry_hint("ArticleSummarizer") == "Use valid JSON only."


@pytest.mark.unit
def test_llm_retry_hints_are_step_scoped() -> None:
    """Hints for different steps do not bleed into each other."""
    context = PipelineContext(
        run_id=uuid4(),
        ticker="TSLA",
        llm_provider=MagicMock(),
    )

    context.set_llm_retry_hint("StepA", "hint-a")
    context.set_llm_retry_hint("StepB", "hint-b")

    assert context.get_llm_retry_hint("StepA") == "hint-a"
    assert context.get_llm_retry_hint("StepB") == "hint-b"
    assert context.get_llm_retry_hint("StepC") is None


@pytest.mark.unit
def test_llm_retry_hint_overwrite() -> None:
    context = PipelineContext(
        run_id=uuid4(),
        ticker="MSFT",
        llm_provider=MagicMock(),
    )

    context.set_llm_retry_hint("step", "first hint")
    context.set_llm_retry_hint("step", "updated hint")

    assert context.get_llm_retry_hint("step") == "updated hint"
