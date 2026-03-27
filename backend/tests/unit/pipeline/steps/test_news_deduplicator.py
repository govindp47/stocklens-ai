"""Unit tests for NewsDeduplicator pipeline step (T-026)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.domain.models.market import CompanyInfo
from app.domain.models.news import RawArticle
from app.pipeline.context import PipelineContext, PipelineOutputs
from app.pipeline.steps.base import StepStatus
from app.pipeline.steps.news_deduplicator import (
    NewsDeduplicator,
    _exact_url_dedup,
    _hamming_distance,
    _simhash,
    _simhash_dedup,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

_NOW = datetime(2024, 1, 15, tzinfo=UTC)


def _article(
    n: int,
    url: str | None = None,
    title: str | None = None,
) -> RawArticle:
    return RawArticle(
        article_id=f"id{n:014d}",
        url=url or f"https://example.com/article/{n}",
        title=title or f"Unique headline number {n} about the stock market",
        published_at=_NOW,
        source_name="TestSource",
    )


def _make_context(
    raw_articles: list[RawArticle] | None = None,
    set_company_info: bool = True,
) -> PipelineContext:
    outputs = PipelineOutputs()
    outputs.raw_articles = raw_articles
    if set_company_info:
        outputs.company_info = CompanyInfo(ticker="AAPL", name="Apple Inc.")
    return PipelineContext(
        run_id=uuid4(),
        ticker="AAPL",
        llm_provider=MagicMock(),
        outputs=outputs,
    )


# ── Metadata ──────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestMetadata:
    def test_step_metadata(self) -> None:
        dedup = NewsDeduplicator()
        assert dedup.name == "NewsDeduplicator"
        assert dedup.step_index == 4
        assert dedup.critical is False
        assert dedup.max_retries == 0


# ── can_execute ───────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestCanExecute:
    def test_skipped_when_no_articles(self) -> None:
        """can_execute returns False when raw_articles is None (Step 3 not run)."""
        dedup = NewsDeduplicator()
        ctx = _make_context(raw_articles=None)
        assert dedup.can_execute(ctx) is False

    def test_can_execute_with_empty_list(self) -> None:
        """Empty list (Step 3 ran, zero results) is a valid input."""
        dedup = NewsDeduplicator()
        ctx = _make_context(raw_articles=[])
        assert dedup.can_execute(ctx) is True

    def test_can_execute_with_articles(self) -> None:
        dedup = NewsDeduplicator()
        ctx = _make_context(raw_articles=[_article(1)])
        assert dedup.can_execute(ctx) is True


# ── Hamming distance ──────────────────────────────────────────────────────────


@pytest.mark.unit
class TestHammingDistance:
    def test_hamming_distance_zero_for_identical(self) -> None:
        assert _hamming_distance(0xDEADBEEF, 0xDEADBEEF) == 0

    def test_hamming_distance_correct_for_known_pair(self) -> None:
        # 0b1010 XOR 0b1001 = 0b0011 → 2 differing bits
        assert _hamming_distance(0b1010, 0b1001) == 2

    def test_hamming_distance_all_bits_differ(self) -> None:
        # All 64 bits differ
        a = 0xFFFF_FFFF_FFFF_FFFF
        b = 0x0000_0000_0000_0000
        assert _hamming_distance(a, b) == 64

    def test_hamming_distance_single_bit(self) -> None:
        assert _hamming_distance(0, 1) == 1


# ── SimHash ───────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestSimHash:
    def test_simhash_deterministic(self) -> None:
        """Same input always produces the same fingerprint."""
        text = "Apple reports record quarterly earnings"
        assert _simhash(text) == _simhash(text)

    def test_simhash_different_texts_differ(self) -> None:
        """Completely unrelated texts produce different fingerprints."""
        fp1 = _simhash("Apple reports record quarterly earnings")
        fp2 = _simhash("Federal Reserve raises interest rates unexpectedly")
        assert fp1 != fp2

    def test_simhash_empty_string_returns_zero(self) -> None:
        assert _simhash("") == 0

    def test_simhash_near_duplicate_low_hamming(self) -> None:
        """Titles differing only in capitalisation produce Hamming distance 0.

        SimHash lowercases all tokens before hashing, so capitalisation
        variants are treated as identical fingerprints.
        """
        t1 = "apple beats earnings estimate for the third quarter results"
        t2 = "Apple Beats Earnings Estimate For The Third Quarter Results"
        dist = _hamming_distance(_simhash(t1), _simhash(t2))
        assert dist <= _HAMMING_THRESHOLD

    def test_simhash_distinct_texts_high_hamming(self) -> None:
        """Very different texts have high Hamming distance."""
        t1 = "Apple reports record quarterly earnings"
        t2 = "Earthquake strikes downtown California causing widespread damage"
        dist = _hamming_distance(_simhash(t1), _simhash(t2))
        assert dist > _HAMMING_THRESHOLD

    def test_simhash_is_64_bit_integer(self) -> None:
        fp = _simhash("some text")
        assert 0 <= fp <= 0xFFFF_FFFF_FFFF_FFFF


# ── Pass 1: exact URL deduplication ──────────────────────────────────────────


@pytest.mark.unit
class TestExactUrlDedup:
    def test_exact_url_deduplication(self) -> None:
        """Two articles with the same URL: only the first is retained."""
        a1 = _article(1, url="https://example.com/same")
        a2 = _article(2, url="https://example.com/same")
        result = _exact_url_dedup([a1, a2])
        assert len(result) == 1
        assert result[0].article_id == a1.article_id

    def test_distinct_urls_all_retained(self) -> None:
        articles = [_article(i) for i in range(1, 6)]
        result = _exact_url_dedup(articles)
        assert len(result) == 5

    def test_empty_list_returns_empty(self) -> None:
        assert _exact_url_dedup([]) == []

    def test_preserves_order(self) -> None:
        articles = [_article(i) for i in range(1, 4)]
        result = _exact_url_dedup(articles)
        assert [a.article_id for a in result] == [a.article_id for a in articles]


# ── Pass 2: SimHash near-duplicate removal ────────────────────────────────────


@pytest.mark.unit
class TestSimHashDedup:
    def test_near_duplicate_simhash(self) -> None:
        """Titles differing only in capitalisation/punctuation are near-duplicates."""
        # RSS feeds often publish the same headline with different casing
        a1 = _article(1, title="apple beats earnings estimate for the third quarter results")
        a2 = _article(2, title="Apple Beats Earnings Estimate For The Third Quarter Results")
        result = _simhash_dedup([a1, a2])
        assert len(result) == 1
        assert result[0].article_id == a1.article_id

    def test_distinct_headlines_all_retained(self) -> None:
        """Five completely distinct headlines: all five retained."""
        articles = [
            _article(1, title="Apple reports record quarterly earnings"),
            _article(2, title="Federal Reserve raises interest rates"),
            _article(3, title="Oil prices surge amid supply concerns"),
            _article(4, title="Tesla announces new gigafactory in Mexico"),
            _article(5, title="Google unveils new artificial intelligence model"),
        ]
        result = _simhash_dedup(articles)
        assert len(result) == 5

    def test_empty_list_returns_empty(self) -> None:
        assert _simhash_dedup([]) == []

    def test_identical_title_removed(self) -> None:
        """Two articles with identical titles: only one kept."""
        title = "Apple stock hits all-time high after earnings beat"
        a1 = _article(1, title=title)
        a2 = _article(2, title=title)
        result = _simhash_dedup([a1, a2])
        assert len(result) == 1


# ── Full execute flow ─────────────────────────────────────────────────────────


@pytest.mark.unit
class TestExecute:
    async def test_full_dedup_pass1_and_pass2(self) -> None:
        """Both passes run; duplicates from both passes are removed."""
        # Pass 1 duplicate (same URL)
        a1 = _article(1, url="https://example.com/same", title="Apple beats earnings")
        a2 = _article(2, url="https://example.com/same", title="Apple beats earnings variant")
        # Pass 2 near-duplicate (different URL, same title different casing)
        a3 = _article(3, title="apple beats earnings estimate for the third quarter results")
        a4 = _article(4, title="Apple Beats Earnings Estimate For The Third Quarter Results")
        # Distinct article — always retained
        a5 = _article(5, title="Federal Reserve raises interest rates unexpectedly")

        ctx = _make_context(raw_articles=[a1, a2, a3, a4, a5])
        dedup = NewsDeduplicator()

        result = await dedup.execute(ctx)

        assert result.status == StepStatus.COMPLETE
        assert ctx.outputs.deduplicated_articles is not None
        # a2 removed by pass 1; a4 removed by pass 2; a1, a3, a5 kept
        assert len(ctx.outputs.deduplicated_articles) == 3

    async def test_empty_input_returns_empty_output(self) -> None:
        ctx = _make_context(raw_articles=[])
        dedup = NewsDeduplicator()

        result = await dedup.execute(ctx)

        assert result.status == StepStatus.COMPLETE
        assert ctx.outputs.deduplicated_articles == []

    async def test_output_summary_contains_counts(self) -> None:
        articles = [_article(i) for i in range(1, 4)]
        ctx = _make_context(raw_articles=articles)
        dedup = NewsDeduplicator()

        result = await dedup.execute(ctx)

        assert "input=3" in result.output_summary
        assert "output=" in result.output_summary

    async def test_deduplicated_articles_always_list_not_none(self) -> None:
        """Even with no input, deduplicated_articles is set to [] not None."""
        ctx = _make_context(raw_articles=[])
        dedup = NewsDeduplicator()
        await dedup.execute(ctx)
        assert ctx.outputs.deduplicated_articles is not None


# ── Performance guard ─────────────────────────────────────────────────────────


@pytest.mark.unit
class TestPerformance:
    async def test_dedup_20_articles_under_100ms(self) -> None:
        """Deduplication of 20 articles must complete in < 100ms."""
        import time

        articles = [_article(i) for i in range(1, 21)]
        ctx = _make_context(raw_articles=articles)
        dedup = NewsDeduplicator()

        t0 = time.monotonic()
        await dedup.execute(ctx)
        elapsed_ms = (time.monotonic() - t0) * 1000

        assert elapsed_ms < 100, f"Took {elapsed_ms:.1f}ms — expected < 100ms"


# ── Re-import threshold for test use ─────────────────────────────────────────

from app.pipeline.steps.news_deduplicator import _HAMMING_THRESHOLD  # noqa: E402
