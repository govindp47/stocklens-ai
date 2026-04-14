"""Unit tests for EventExtractor pipeline step (T-036)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.domain.models.events import ExtractedEvent
from app.domain.models.market import CompanyInfo
from app.domain.models.news import ArticleSummary
from app.pipeline.context import PipelineContext, PipelineOutputs
from app.pipeline.steps.base import StepStatus
from app.pipeline.steps.event_extractor import EventExtractor, _deduplicate_events

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_summary(n: int = 1) -> ArticleSummary:
    return ArticleSummary(
        article_id=f"a{n:04d}",
        url=f"https://example.com/{n}",
        title=f"Apple headline {n}",
        published_at=datetime(2024, 3, 1, tzinfo=UTC),
        source_name="Reuters",
        content_snippet="content",
        summary=f"Summary of article {n}.",
        topics=["Earnings"],
        sentiment="positive",
        sentiment_score=0.9,
        summarization_failed=False,
    )


def _make_context(summaries: list[ArticleSummary] | None = None) -> PipelineContext:
    outputs = PipelineOutputs()
    outputs.company_info = CompanyInfo(ticker="AAPL", name="Apple Inc.")
    outputs.article_summaries = summaries
    return PipelineContext(
        run_id=uuid4(),
        ticker="AAPL",
        llm_provider=MagicMock(),
        outputs=outputs,
    )


def _events_response(events: list[dict]) -> str:
    return json.dumps({"events": events})


def _make_extractor() -> tuple[EventExtractor, MagicMock]:
    mock_loader = MagicMock()
    mock_loader.render.return_value = "rendered events prompt"
    return EventExtractor(prompt_loader=mock_loader), mock_loader


_VALID_EVENT = {
    "event_type": "Earnings Announcement",
    "description": "Apple reported Q4 earnings above expectations.",
    "detected_date": "2024-03-01",
    "source_article_indices": [1, 2],
}


# ── Metadata ──────────────────────────────────────────────────────────────────


@pytest.mark.unit()
class TestMetadata:
    def test_step_metadata(self) -> None:
        extractor, _ = _make_extractor()
        assert extractor.name == "EventExtractor"
        assert extractor.step_index == 7
        assert extractor.critical is False
        assert extractor.max_retries == 2


# ── can_execute ───────────────────────────────────────────────────────────────


@pytest.mark.unit()
class TestCanExecute:
    def test_can_execute_false_without_summaries(self) -> None:
        extractor, _ = _make_extractor()
        ctx = _make_context(summaries=None)
        assert extractor.can_execute(ctx) is False

    def test_can_execute_true_with_empty_list(self) -> None:
        extractor, _ = _make_extractor()
        ctx = _make_context(summaries=[])
        assert extractor.can_execute(ctx) is True

    def test_can_execute_true_with_summaries(self) -> None:
        extractor, _ = _make_extractor()
        ctx = _make_context(summaries=[_make_summary(1)])
        assert extractor.can_execute(ctx) is True


# ── Valid events extracted ────────────────────────────────────────────────────


@pytest.mark.unit()
class TestValidEventsExtracted:
    async def test_valid_events_extracted(self) -> None:
        ctx = _make_context(summaries=[_make_summary(1)])
        ctx.llm_provider.complete = AsyncMock(return_value=_events_response([_VALID_EVENT]))

        extractor, _ = _make_extractor()
        result = await extractor.execute(ctx)

        assert result.status == StepStatus.COMPLETE
        assert ctx.outputs.events is not None
        assert len(ctx.outputs.events) == 1
        assert ctx.outputs.events[0].event_type == "Earnings Announcement"
        assert ctx.outputs.events[0].detected_date == "2024-03-01"

    async def test_events_count_in_output_summary(self) -> None:
        ctx = _make_context(summaries=[_make_summary(1)])
        ctx.llm_provider.complete = AsyncMock(return_value=_events_response([_VALID_EVENT]))

        extractor, _ = _make_extractor()
        result = await extractor.execute(ctx)

        assert "events=1" in result.output_summary

    async def test_multiple_valid_events(self) -> None:
        events = [
            _VALID_EVENT,
            {
                "event_type": "Product Launch",
                "description": "Apple launched the Vision Pro.",
                "detected_date": "2024-02-02",
                "source_article_indices": [3],
            },
        ]
        ctx = _make_context(summaries=[_make_summary(1)])
        ctx.llm_provider.complete = AsyncMock(return_value=_events_response(events))

        extractor, _ = _make_extractor()
        result = await extractor.execute(ctx)

        assert result.status == StepStatus.COMPLETE
        assert ctx.outputs.events is not None
        assert len(ctx.outputs.events) == 2


# ── Invalid event type discarded ──────────────────────────────────────────────


@pytest.mark.unit()
class TestInvalidEventTypeDiscarded:
    async def test_invalid_event_type_discarded(self) -> None:
        """Events with event_type not in the allowed list are silently discarded."""
        events = [
            {
                "event_type": "Stock Buyback",  # not in allowed list
                "description": "Apple announced a massive stock buyback.",
                "detected_date": "2024-03-01",
                "source_article_indices": [1],
            },
            _VALID_EVENT,  # valid
        ]
        ctx = _make_context(summaries=[_make_summary(1)])
        ctx.llm_provider.complete = AsyncMock(return_value=_events_response(events))

        extractor, _ = _make_extractor()
        await extractor.execute(ctx)

        assert ctx.outputs.events is not None
        assert len(ctx.outputs.events) == 1
        assert ctx.outputs.events[0].event_type == "Earnings Announcement"

    async def test_all_invalid_types_gives_empty_list(self) -> None:
        events = [
            {
                "event_type": "Unknown",
                "description": "Something happened.",
                "detected_date": None,
                "source_article_indices": [],
            },
        ]
        ctx = _make_context(summaries=[_make_summary(1)])
        ctx.llm_provider.complete = AsyncMock(return_value=_events_response(events))

        extractor, _ = _make_extractor()
        result = await extractor.execute(ctx)

        assert result.status == StepStatus.COMPLETE
        assert ctx.outputs.events == []


# ── Empty events → COMPLETE ───────────────────────────────────────────────────


@pytest.mark.unit()
class TestEmptyEvents:
    async def test_empty_events_is_complete_not_failed(self) -> None:
        """Empty events array from model produces COMPLETE, not FAILED."""
        ctx = _make_context(summaries=[_make_summary(1)])
        ctx.llm_provider.complete = AsyncMock(return_value=_events_response([]))

        extractor, _ = _make_extractor()
        result = await extractor.execute(ctx)

        assert result.status == StepStatus.COMPLETE
        assert ctx.outputs.events == []

    async def test_empty_description_events_discarded(self) -> None:
        events = [
            {
                "event_type": "Earnings Announcement",
                "description": "",
                "detected_date": None,
                "source_article_indices": [],
            },
        ]
        ctx = _make_context(summaries=[_make_summary(1)])
        ctx.llm_provider.complete = AsyncMock(return_value=_events_response(events))

        extractor, _ = _make_extractor()
        await extractor.execute(ctx)

        assert ctx.outputs.events == []


# ── Deduplication ─────────────────────────────────────────────────────────────


@pytest.mark.unit()
class TestDeduplication:
    async def test_identical_descriptions_merged(self) -> None:
        """Duplicate descriptions are merged by combining source_article_indices."""
        events = [
            {
                "event_type": "Earnings Announcement",
                "description": "Apple beat Q4 earnings.",
                "detected_date": "2024-03-01",
                "source_article_indices": [1],
            },
            {
                "event_type": "Earnings Announcement",
                "description": "Apple beat Q4 earnings.",  # same description
                "detected_date": "2024-03-01",
                "source_article_indices": [2, 3],
            },
        ]
        ctx = _make_context(summaries=[_make_summary(1)])
        ctx.llm_provider.complete = AsyncMock(return_value=_events_response(events))

        extractor, _ = _make_extractor()
        await extractor.execute(ctx)

        assert ctx.outputs.events is not None
        assert len(ctx.outputs.events) == 1  # merged
        merged = ctx.outputs.events[0]
        assert set(merged.source_article_indices) == {1, 2, 3}

    def test_deduplicate_events_directly(self) -> None:
        events = [
            ExtractedEvent(
                event_type="Earnings Announcement",
                description="Apple beat earnings.",
                detected_date="2024-03-01",
                source_article_indices=[1],
            ),
            ExtractedEvent(
                event_type="Earnings Announcement",
                description="Apple beat earnings.",
                detected_date="2024-03-01",
                source_article_indices=[2],
            ),
            ExtractedEvent(
                event_type="Product Launch",
                description="Different event.",
                detected_date="2024-03-02",
                source_article_indices=[3],
            ),
        ]
        result = _deduplicate_events(events)
        assert len(result) == 2
        assert set(result[0].source_article_indices) == {1, 2}
        assert result[1].description == "Different event."

    def test_no_duplicates_unchanged(self) -> None:
        events = [
            ExtractedEvent(
                event_type="Product Launch",
                description="Unique event A.",
                detected_date="2024-03-01",
                source_article_indices=[1],
            ),
            ExtractedEvent(
                event_type="Leadership Change",
                description="Unique event B.",
                detected_date="2024-03-02",
                source_article_indices=[2],
            ),
        ]
        result = _deduplicate_events(events)
        assert len(result) == 2


# ── Article cap ───────────────────────────────────────────────────────────────


@pytest.mark.unit()
class TestArticleCap:
    async def test_article_list_capped_at_20(self) -> None:
        """Template receives at most 20 articles regardless of input size."""
        summaries = [_make_summary(i) for i in range(1, 26)]  # 25 articles
        ctx = _make_context(summaries=summaries)
        ctx.llm_provider.complete = AsyncMock(return_value=_events_response([]))

        extractor, mock_loader = _make_extractor()
        await extractor.execute(ctx)

        # render was called once with articles list
        call_kwargs = mock_loader.render.call_args
        assert call_kwargs is not None
        # Access the articles kwarg
        rendered_call = mock_loader.render.call_args
        articles = rendered_call.kwargs["articles"]
        assert len(articles) <= 20


# ── Event cap ────────────────────────────────────────────────────────────────


@pytest.mark.unit()
class TestEventCap:
    async def test_events_capped_at_10(self) -> None:
        """Output is capped at 10 events even if model returns more."""
        events = [
            {
                "event_type": "Product Launch",
                "description": f"Apple launched product {i}.",
                "detected_date": "2024-03-01",
                "source_article_indices": [i],
            }
            for i in range(1, 16)  # 15 events
        ]
        ctx = _make_context(summaries=[_make_summary(1)])
        ctx.llm_provider.complete = AsyncMock(return_value=_events_response(events))

        extractor, _ = _make_extractor()
        await extractor.execute(ctx)

        assert ctx.outputs.events is not None
        assert len(ctx.outputs.events) <= 10


# ── Date validation ───────────────────────────────────────────────────────────


@pytest.mark.unit()
class TestDateValidation:
    async def test_invalid_date_stored_as_empty_string(self) -> None:
        events = [
            {
                "event_type": "Product Launch",
                "description": "Something launched.",
                "detected_date": "not-a-date",
                "source_article_indices": [1],
            }
        ]
        ctx = _make_context(summaries=[_make_summary(1)])
        ctx.llm_provider.complete = AsyncMock(return_value=_events_response(events))

        extractor, _ = _make_extractor()
        await extractor.execute(ctx)

        assert ctx.outputs.events is not None
        assert ctx.outputs.events[0].detected_date == ""

    async def test_null_date_stored_as_empty_string(self) -> None:
        events = [
            {
                "event_type": "Leadership Change",
                "description": "New CEO appointed.",
                "detected_date": None,
                "source_article_indices": [1],
            }
        ]
        ctx = _make_context(summaries=[_make_summary(1)])
        ctx.llm_provider.complete = AsyncMock(return_value=_events_response(events))

        extractor, _ = _make_extractor()
        await extractor.execute(ctx)

        assert ctx.outputs.events is not None
        assert ctx.outputs.events[0].detected_date == ""


# ── Retry hint appended ───────────────────────────────────────────────────────


@pytest.mark.unit()
class TestRetryHint:
    async def test_retry_hint_appended_to_prompt(self) -> None:
        """When orchestrator sets a retry hint, it is appended to the prompt."""
        ctx = _make_context(summaries=[_make_summary(1)])
        ctx.set_llm_retry_hint("EventExtractor", "RETRY HINT TEXT")
        ctx.llm_provider.complete = AsyncMock(return_value=_events_response([]))

        extractor, mock_loader = _make_extractor()
        mock_loader.render.return_value = "base prompt"

        captured_prompts: list[str] = []

        async def capture_prompt(prompt: str, **kwargs: object) -> str:
            captured_prompts.append(prompt)
            return _events_response([])

        ctx.llm_provider.complete = capture_prompt
        await extractor.execute(ctx)

        assert len(captured_prompts) == 1
        assert "RETRY HINT TEXT" in captured_prompts[0]
