"""Unit tests for domain models.

Tests:
  - Valid instantiation of every model.
  - Required field enforcement (ValidationError on missing required fields).
  - SentimentDistribution sum-to-100 validator.
  - AnalysisReport.completeness is a Literal["complete","partial","minimal"].
  - InsightsResult.disclaimer is populated from constant, not from LLM output.
  - content_hash is auto-computed on AnalysisReport.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.domain.exceptions import (
    ExternalProviderError,
    LLMParseError,
    PipelineTimeoutError,
    RateLimitExceededError,
    TickerNotResolvableError,
)
from app.domain.models.events import EventsResult, ExtractedEvent
from app.domain.models.insights import InsightSections, InsightsResult
from app.domain.models.market import CompanyInfo, MarketData, PriceHistory, PricePoint
from app.domain.models.news import ArticleSummary, NewsCollection, RawArticle
from app.domain.models.report import AnalysisReport
from app.domain.models.sentiment import SentimentDistribution, SentimentResult
from app.lib.constants import AI_ANALYSIS_DISCLAIMER

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _raw_article() -> RawArticle:
    return RawArticle(
        article_id="a1",
        url="https://example.com/article",
        title="Apple Reports Record Revenue",
        published_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
        source_name="Reuters",
        content_snippet="Apple Inc reported record quarterly revenue...",
    )


def _article_summary() -> ArticleSummary:
    return ArticleSummary(
        article_id="a1",
        url="https://example.com/article",
        title="Apple Reports Record Revenue",
        published_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
        source_name="Reuters",
        content_snippet="Apple Inc reported record quarterly revenue...",
        summary="Apple beat revenue expectations for Q1 2024.",
        topics=["earnings", "revenue"],
        sentiment="positive",
        sentiment_score=0.85,
    )


def _minimal_report(
    completeness: str = "complete",
) -> AnalysisReport:
    return AnalysisReport(
        run_id=uuid.uuid4(),
        ticker="AAPL",
        company=CompanyInfo(ticker="AAPL", name="Apple Inc."),
        completeness=completeness,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# CompanyInfo
# ---------------------------------------------------------------------------


class TestCompanyInfo:
    def test_valid_instantiation(self) -> None:
        info = CompanyInfo(ticker="AAPL", name="Apple Inc.", exchange="NASDAQ")
        assert info.ticker == "AAPL"
        assert info.name == "Apple Inc."
        assert info.exchange == "NASDAQ"

    def test_optional_fields_default_none(self) -> None:
        info = CompanyInfo(ticker="AAPL")
        assert info.name is None
        assert info.sector is None

    def test_missing_required_ticker_raises(self) -> None:
        with pytest.raises(ValidationError):
            CompanyInfo()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# MarketData
# ---------------------------------------------------------------------------


class TestMarketData:
    def test_valid_full_instantiation(self) -> None:
        md = MarketData(
            available=True,
            price=175.5,
            change_pct=1.2,
            change_abs=2.1,
            volume=50_000_000.0,
            market_cap=2_700_000_000_000.0,
            pe_ratio=28.5,
            week_52_high=199.62,
            week_52_low=124.17,
            currency="USD",
        )
        assert md.available is True
        assert md.price == 175.5

    def test_all_numeric_fields_nullable(self) -> None:
        md = MarketData(available=False)
        assert md.price is None
        assert md.pe_ratio is None


# ---------------------------------------------------------------------------
# PricePoint and PriceHistory
# ---------------------------------------------------------------------------


class TestPricePoint:
    def test_valid_instantiation(self) -> None:
        pp = PricePoint(
            date="2024-01-15", open=174.0, high=176.0, low=173.0, close=175.5, volume=45_000_000.0
        )
        assert pp.date == "2024-01-15"
        assert pp.close == 175.5

    def test_missing_date_raises(self) -> None:
        with pytest.raises(ValidationError):
            PricePoint()  # type: ignore[call-arg]


class TestPriceHistory:
    def test_valid_with_datapoints(self) -> None:
        ph = PriceHistory(
            available=True,
            datapoints=[PricePoint(date="2024-01-15")],
            trend_direction="up",
            volatility_flag=False,
        )
        assert ph.available is True
        assert len(ph.datapoints) == 1

    def test_defaults_to_empty(self) -> None:
        ph = PriceHistory()
        assert ph.available is False
        assert ph.datapoints == []


# ---------------------------------------------------------------------------
# RawArticle and ArticleSummary
# ---------------------------------------------------------------------------


class TestRawArticle:
    def test_valid_instantiation(self) -> None:
        article = _raw_article()
        assert article.article_id == "a1"
        assert article.source_name == "Reuters"

    def test_missing_required_fields_raise(self) -> None:
        with pytest.raises(ValidationError):
            RawArticle(title="Missing fields")  # type: ignore[call-arg]


class TestArticleSummary:
    def test_extends_raw_article(self) -> None:
        summary = _article_summary()
        assert summary.title == "Apple Reports Record Revenue"
        assert summary.sentiment == "positive"
        assert summary.summarization_failed is False

    def test_summarization_failed_flag(self) -> None:
        article = ArticleSummary(
            article_id="a2",
            url="https://example.com/b",
            title="Failed Article",
            published_at=datetime(2024, 1, 10, tzinfo=UTC),
            source_name="Bloomberg",
            summarization_failed=True,
        )
        assert article.summarization_failed is True
        assert article.summary == ""


class TestNewsCollection:
    def test_valid_with_articles(self) -> None:
        nc = NewsCollection(available=True, articles=[_article_summary()])
        assert nc.available is True
        assert len(nc.articles) == 1

    def test_default_empty(self) -> None:
        nc = NewsCollection()
        assert nc.articles == []


# ---------------------------------------------------------------------------
# SentimentDistribution
# ---------------------------------------------------------------------------


class TestSentimentDistribution:
    def test_valid_sums_to_100(self) -> None:
        sd = SentimentDistribution(positive=60, neutral=30, negative=10)
        assert sd.positive == 60

    def test_raises_when_not_100(self) -> None:
        with pytest.raises(ValidationError, match="sum to 100"):
            SentimentDistribution(positive=50, neutral=30, negative=10)

    def test_all_zero_raises(self) -> None:
        with pytest.raises(ValidationError):
            SentimentDistribution(positive=0, neutral=0, negative=0)

    def test_boundary_100_neutral(self) -> None:
        sd = SentimentDistribution(positive=0, neutral=100, negative=0)
        assert sd.neutral == 100


class TestSentimentResult:
    def test_valid_instantiation(self) -> None:
        sd = SentimentDistribution(positive=70, neutral=20, negative=10)
        sr = SentimentResult(
            available=True,
            distribution=sd,
            dominant="positive",
            article_count=15,
        )
        assert sr.dominant == "positive"
        assert sr.article_count == 15

    def test_default_unavailable(self) -> None:
        sr = SentimentResult()
        assert sr.available is False
        assert sr.distribution is None


# ---------------------------------------------------------------------------
# ExtractedEvent and EventsResult
# ---------------------------------------------------------------------------


class TestExtractedEvent:
    def test_valid_instantiation(self) -> None:
        event = ExtractedEvent(
            event_type="earnings",
            description="Q1 2024 earnings beat expectations by 5%.",
            detected_date="2024-01-15",
            source_article_indices=[0, 2],
        )
        assert event.event_type == "earnings"
        assert event.source_article_indices == [0, 2]

    def test_missing_required_fields_raise(self) -> None:
        with pytest.raises(ValidationError):
            ExtractedEvent(event_type="earnings")  # type: ignore[call-arg]


class TestEventsResult:
    def test_with_events(self) -> None:
        ev = ExtractedEvent(
            event_type="acquisition",
            description="Company acquired a startup.",
            detected_date="2024-01-20",
        )
        er = EventsResult(available=True, events=[ev])
        assert er.available is True
        assert len(er.events) == 1

    def test_default_empty(self) -> None:
        er = EventsResult()
        assert er.events == []


# ---------------------------------------------------------------------------
# InsightSections and InsightsResult
# ---------------------------------------------------------------------------


class TestInsightSections:
    def test_valid_instantiation(self) -> None:
        sections = InsightSections(
            company_overview="Apple is a tech giant.",
            recent_developments="New iPhone released.",
            sentiment_overview="Broadly positive.",
            potential_drivers="Strong services growth.",
            potential_risks="China market headwinds.",
            ai_summary="Apple shows resilient fundamentals.",
        )
        assert sections.company_overview == "Apple is a tech giant."


class TestInsightsResult:
    def test_disclaimer_from_constant(self) -> None:
        ir = InsightsResult(available=True, sections=InsightSections())
        assert ir.disclaimer == AI_ANALYSIS_DISCLAIMER

    def test_disclaimer_is_not_empty(self) -> None:
        ir = InsightsResult()
        assert len(ir.disclaimer) > 0

    def test_disclaimer_cannot_be_overridden_to_empty(self) -> None:
        """Disclaimer should default to the constant; explicit override still validates."""
        ir = InsightsResult(disclaimer="custom override")
        assert ir.disclaimer == "custom override"


# ---------------------------------------------------------------------------
# AnalysisReport
# ---------------------------------------------------------------------------


class TestAnalysisReport:
    def test_valid_minimal_instantiation(self) -> None:
        report = _minimal_report()
        assert report.ticker == "AAPL"
        assert report.completeness == "complete"

    def test_completeness_literal_complete(self) -> None:
        report = _minimal_report(completeness="complete")
        assert report.completeness == "complete"

    def test_completeness_literal_partial(self) -> None:
        report = _minimal_report(completeness="partial")
        assert report.completeness == "partial"

    def test_completeness_literal_minimal(self) -> None:
        report = _minimal_report(completeness="minimal")
        assert report.completeness == "minimal"

    def test_completeness_invalid_value_raises(self) -> None:
        with pytest.raises(ValidationError):
            AnalysisReport(
                run_id=uuid.uuid4(),
                ticker="AAPL",
                company=CompanyInfo(ticker="AAPL"),
                completeness="unknown",  # type: ignore[arg-type]
            )

    def test_content_hash_is_computed(self) -> None:
        report = _minimal_report()
        assert report.content_hash is not None
        assert len(report.content_hash) == 64  # SHA-256 hex digest

    def test_content_hash_is_deterministic_for_same_data(self) -> None:
        run_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
        ts = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        r1 = AnalysisReport(
            run_id=run_id,
            ticker="AAPL",
            company=CompanyInfo(ticker="AAPL"),
            generated_at=ts,
        )
        r2 = AnalysisReport(
            run_id=run_id,
            ticker="AAPL",
            company=CompanyInfo(ticker="AAPL"),
            generated_at=ts,
        )
        assert r1.content_hash == r2.content_hash

    def test_schema_version_populated(self) -> None:
        report = _minimal_report()
        assert report.schema_version != ""

    def test_missing_required_fields_raise(self) -> None:
        with pytest.raises(ValidationError):
            AnalysisReport(ticker="AAPL")  # type: ignore[call-arg]

    def test_partial_data_and_error_notices(self) -> None:
        report = AnalysisReport(
            run_id=uuid.uuid4(),
            ticker="MSFT",
            company=CompanyInfo(ticker="MSFT"),
            completeness="partial",
            partial_data_notices=["Price history unavailable"],
            error_notices=["yfinance timeout after 10s"],
        )
        assert "Price history unavailable" in report.partial_data_notices
        assert "yfinance timeout after 10s" in report.error_notices


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class TestExceptions:
    def test_external_provider_error_defaults(self) -> None:
        err = ExternalProviderError(
            "Provider failed",
            error_code="YFINANCE_TIMEOUT",
            user_message="Market data is temporarily unavailable.",
        )
        assert err.is_retryable is True
        assert err.error_code == "YFINANCE_TIMEOUT"

    def test_external_provider_error_not_retryable(self) -> None:
        err = ExternalProviderError(
            "Auth failed",
            error_code="OPENAI_AUTH_FAILED",
            user_message="LLM provider authentication failed.",
            is_retryable=False,
        )
        assert err.is_retryable is False

    def test_llm_parse_error_stores_raw_output(self) -> None:
        raw = '{"invalid": json}'
        err = LLMParseError("Parse failed", step_name="SentimentClassifier", raw_output=raw)
        assert err.step_name == "SentimentClassifier"
        assert err.raw_output == raw

    def test_pipeline_timeout_error(self) -> None:
        err = PipelineTimeoutError("Run timed out after 90s")
        assert isinstance(err, PipelineTimeoutError)

    def test_ticker_not_resolvable_error(self) -> None:
        err = TickerNotResolvableError("BADTICKER is not resolvable")
        assert isinstance(err, TickerNotResolvableError)

    def test_rate_limit_exceeded_error(self) -> None:
        err = RateLimitExceededError("Too many requests")
        assert isinstance(err, RateLimitExceededError)

    def test_all_exceptions_inherit_base(self) -> None:
        from app.domain.exceptions import StockLensBaseError

        for exc_class in [
            ExternalProviderError,
            PipelineTimeoutError,
            TickerNotResolvableError,
            RateLimitExceededError,
        ]:
            assert issubclass(exc_class, StockLensBaseError)
