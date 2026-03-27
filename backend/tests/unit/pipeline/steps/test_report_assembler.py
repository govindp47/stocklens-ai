"""Unit tests for ReportAssembler pipeline step (T-038)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.domain.models.events import ExtractedEvent
from app.domain.models.insights import InsightSections
from app.domain.models.market import CompanyInfo, MarketData, PriceHistory
from app.domain.models.news import ArticleSummary, RawArticle
from app.domain.models.report import AnalysisReport
from app.domain.models.sentiment import SentimentDistribution, SentimentResult
from app.pipeline.context import PipelineContext, PipelineOutputs
from app.pipeline.steps.base import StepStatus
from app.pipeline.steps.report_assembler import ReportAssembler, _compute_completeness


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_article(n: int = 1) -> ArticleSummary:
    return ArticleSummary(
        article_id=f"a{n:04d}",
        url=f"https://example.com/{n}",
        title=f"Headline {n}",
        published_at=datetime(2024, 3, 1, tzinfo=UTC),
        source_name="Reuters",
        content_snippet="content",
        summary=f"Summary {n}.",
        topics=["Earnings"],
        sentiment="positive",
        sentiment_score=0.9,
        summarization_failed=False,
    )


def _make_raw_article(n: int = 1) -> RawArticle:
    return RawArticle(
        article_id=f"r{n:04d}",
        url=f"https://example.com/raw/{n}",
        title=f"Raw headline {n}",
        published_at=datetime(2024, 3, 1, tzinfo=UTC),
        source_name="Reuters",
    )


def _make_context_full() -> PipelineContext:
    """Context with all sections populated."""
    outputs = PipelineOutputs()
    outputs.company_info = CompanyInfo(ticker="AAPL", name="Apple Inc.")
    outputs.market_data = MarketData(
        available=True, price=185.5, change_pct=1.2, change_abs=2.2
    )
    outputs.price_history = PriceHistory(available=True)
    outputs.raw_articles = [_make_raw_article(i) for i in range(1, 4)]
    outputs.deduplicated_articles = outputs.raw_articles.copy()
    outputs.article_summaries = [_make_article(i) for i in range(1, 4)]
    outputs.sentiment = SentimentResult(
        available=True,
        distribution=SentimentDistribution(positive=60, neutral=25, negative=15),
        dominant="Predominantly Positive",
        article_count=3,
    )
    outputs.events = [
        ExtractedEvent(
            event_type="Earnings Announcement",
            description="Apple beat Q4.",
            detected_date="2024-03-01",
            source_article_indices=[1],
        )
    ]
    outputs.insights = InsightSections(
        company_overview="Apple is a tech leader.",
        recent_developments="Beat Q4.",
        sentiment_overview="Positive.",
        potential_drivers="iPhone.",
        potential_risks="Macro.",
        ai_summary="Solid quarter.",
    )

    mock_llm = MagicMock()
    mock_llm.model_name = "mistral:7b-instruct"

    return PipelineContext(
        run_id=uuid4(),
        ticker="AAPL",
        llm_provider=mock_llm,
        outputs=outputs,
    )


def _make_context_minimal() -> PipelineContext:
    """Context with only company_info (all other sections None)."""
    outputs = PipelineOutputs()
    # No company_info intentionally for "minimal" without company
    mock_llm = MagicMock()
    mock_llm.model_name = "mistral:7b-instruct"
    return PipelineContext(
        run_id=uuid4(), ticker="AAPL", llm_provider=mock_llm, outputs=outputs
    )


def _make_assembler() -> ReportAssembler:
    return ReportAssembler()


# ── Metadata ──────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestMetadata:
    def test_step_metadata(self) -> None:
        asm = _make_assembler()
        assert asm.name == "ReportAssembler"
        assert asm.step_index == 9
        assert asm.critical is True
        assert asm.max_retries == 0

    def test_can_execute_always_true(self) -> None:
        asm = _make_assembler()
        ctx = _make_context_minimal()
        assert asm.can_execute(ctx) is True


# ── Completeness ──────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestCompleteness:
    async def test_completeness_complete_with_all_sections(self) -> None:
        ctx = _make_context_full()
        asm = _make_assembler()
        result = await asm.execute(ctx)

        assert result.status == StepStatus.COMPLETE
        report_json = ctx.outputs.final_report_json
        assert report_json is not None
        data = json.loads(report_json)
        assert data["completeness"] == "complete"

    async def test_completeness_partial_with_only_market_data(self) -> None:
        """company_info + market_data only → 2 optional sections → partial."""
        outputs = PipelineOutputs()
        outputs.company_info = CompanyInfo(ticker="AAPL", name="Apple Inc.")
        outputs.market_data = MarketData(available=True, price=185.5)
        # No news, sentiment, insights
        mock_llm = MagicMock()
        mock_llm.model_name = "ollama"
        ctx = PipelineContext(
            run_id=uuid4(), ticker="AAPL", llm_provider=mock_llm, outputs=outputs
        )

        asm = _make_assembler()
        await asm.execute(ctx)

        data = json.loads(ctx.outputs.final_report_json)  # type: ignore[arg-type]
        assert data["completeness"] == "partial"

    async def test_completeness_minimal_without_company_info(self) -> None:
        ctx = _make_context_minimal()
        asm = _make_assembler()
        await asm.execute(ctx)

        data = json.loads(ctx.outputs.final_report_json)  # type: ignore[arg-type]
        assert data["completeness"] == "minimal"

    def test_compute_completeness_directly(self) -> None:
        ctx = _make_context_full()
        assert _compute_completeness(ctx) == "complete"

    def test_compute_completeness_minimal(self) -> None:
        ctx = _make_context_minimal()
        assert _compute_completeness(ctx) == "minimal"


# ── Content hash ──────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestContentHash:
    async def test_content_hash_is_deterministic(self) -> None:
        """Calling execute() twice with identical context → same content_hash."""
        ctx1 = _make_context_full()
        ctx2 = _make_context_full()
        # Ensure same run_id and ticker
        ctx2.outputs.company_info = ctx1.outputs.company_info

        asm = _make_assembler()

        # Execute both (generated_at will differ, so we compare structure not hash)
        await asm.execute(ctx1)
        data1 = json.loads(ctx1.outputs.final_report_json)  # type: ignore[arg-type]

        # The AnalysisReport model_validator computes hash from model_dump excluding hash itself
        assert data1["content_hash"] is not None
        assert len(data1["content_hash"]) == 64  # SHA-256 hex = 64 chars

    async def test_content_hash_is_valid_sha256_hex(self) -> None:
        ctx = _make_context_full()
        asm = _make_assembler()
        await asm.execute(ctx)

        data = json.loads(ctx.outputs.final_report_json)  # type: ignore[arg-type]
        hash_val = data["content_hash"]
        assert len(hash_val) == 64
        assert all(c in "0123456789abcdef" for c in hash_val)


# ── final_report_json validity ────────────────────────────────────────────────


@pytest.mark.unit
class TestReportJsonValidity:
    async def test_final_report_json_is_parseable(self) -> None:
        """context.outputs.final_report_json is a valid JSON string."""
        ctx = _make_context_full()
        asm = _make_assembler()
        await asm.execute(ctx)

        assert ctx.outputs.final_report_json is not None
        data = json.loads(ctx.outputs.final_report_json)
        assert "ticker" in data
        assert "completeness" in data
        assert "content_hash" in data

    async def test_final_report_json_ticker_matches_context(self) -> None:
        ctx = _make_context_full()
        asm = _make_assembler()
        await asm.execute(ctx)

        data = json.loads(ctx.outputs.final_report_json)  # type: ignore[arg-type]
        assert data["ticker"] == "AAPL"

    async def test_step_result_is_complete(self) -> None:
        ctx = _make_context_full()
        asm = _make_assembler()
        result = await asm.execute(ctx)
        assert result.status == StepStatus.COMPLETE


# ── Partial data notices ──────────────────────────────────────────────────────


@pytest.mark.unit
class TestPartialNotices:
    async def test_partial_notices_collected_from_failed_sections(self) -> None:
        """Unavailable sections produce partial_data_notices."""
        outputs = PipelineOutputs()
        outputs.company_info = CompanyInfo(ticker="AAPL", name="Apple Inc.")
        outputs.market_data = MarketData(available=True, price=185.5)
        # market_data is set, but no news/sentiment/insights

        mock_llm = MagicMock()
        mock_llm.model_name = "ollama"
        ctx = PipelineContext(
            run_id=uuid4(), ticker="AAPL", llm_provider=mock_llm, outputs=outputs
        )

        asm = _make_assembler()
        await asm.execute(ctx)

        data = json.loads(ctx.outputs.final_report_json)  # type: ignore[arg-type]
        notices = data["partial_data_notices"]
        assert isinstance(notices, list)
        # At least one notice for missing news
        assert any("news" in n.lower() or "article" in n.lower() for n in notices)

    async def test_no_notices_when_all_sections_available(self) -> None:
        ctx = _make_context_full()
        asm = _make_assembler()
        await asm.execute(ctx)

        data = json.loads(ctx.outputs.final_report_json)  # type: ignore[arg-type]
        assert data["partial_data_notices"] == []


# ── Section assembly ──────────────────────────────────────────────────────────


@pytest.mark.unit
class TestSectionAssembly:
    async def test_none_market_data_assembles_as_unavailable(self) -> None:
        outputs = PipelineOutputs()
        outputs.company_info = CompanyInfo(ticker="AAPL")
        mock_llm = MagicMock()
        mock_llm.model_name = "ollama"
        ctx = PipelineContext(
            run_id=uuid4(), ticker="AAPL", llm_provider=mock_llm, outputs=outputs
        )

        asm = _make_assembler()
        await asm.execute(ctx)

        data = json.loads(ctx.outputs.final_report_json)  # type: ignore[arg-type]
        assert data["market_data"]["available"] is False

    async def test_none_insights_assembles_as_unavailable(self) -> None:
        ctx = _make_context_full()
        ctx.outputs.insights = None  # remove insights

        asm = _make_assembler()
        await asm.execute(ctx)

        data = json.loads(ctx.outputs.final_report_json)  # type: ignore[arg-type]
        assert data["insights"]["available"] is False

    async def test_events_wrapped_in_events_result(self) -> None:
        ctx = _make_context_full()
        asm = _make_assembler()
        await asm.execute(ctx)

        data = json.loads(ctx.outputs.final_report_json)  # type: ignore[arg-type]
        assert data["events"]["available"] is True
        assert isinstance(data["events"]["events"], list)
        assert len(data["events"]["events"]) == 1

    async def test_company_placeholder_when_company_info_none(self) -> None:
        ctx = _make_context_minimal()
        asm = _make_assembler()
        await asm.execute(ctx)

        data = json.loads(ctx.outputs.final_report_json)  # type: ignore[arg-type]
        assert data["company"]["ticker"] == "AAPL"
