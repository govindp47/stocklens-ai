"""Step 7 — EventExtractor (non-critical pipeline step).

Makes a single LLM call on the entire article corpus.  Events are validated
against the six allowed event types; invalid types are silently discarded.
Duplicate descriptions are merged by combining source_article_indices.

Retry behaviour is handled by the orchestrator (max_retries=2):
  On LLMParseError the orchestrator stores a retry hint; this step appends
  it to the prompt on subsequent execute() calls.
"""

from __future__ import annotations

import dataclasses
import logging
import re
import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.exceptions import LLMParseError
from app.domain.models.events import ExtractedEvent
from app.infrastructure.providers.llm_parser import (
    MAX_PROMPT_TOKENS,
    estimate_tokens,
    extract_json,
)
from app.infrastructure.providers.prompt_loader import PromptLoader
from app.pipeline.context import PipelineContext
from app.pipeline.steps.base import BasePipelineStep, StepResult, StepStatus

logger = logging.getLogger(__name__)

# Allowed event type taxonomy (exact strings from events.j2 template)
_ALLOWED_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "Earnings Announcement",
        "Acquisition or Merger",
        "Regulatory Action",
        "Product Launch",
        "Leadership Change",
        "Other Significant Event",
    }
)

_MAX_ARTICLES: int = 20
_MAX_EVENTS: int = 10
_MAX_ENTRY_CHARS: int = 200

# ISO date: YYYY-MM-DD
_ISO_DATE_RE: re.Pattern[str] = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ── Template article helper ───────────────────────────────────────────────────


@dataclasses.dataclass(frozen=True)
class _TemplateArticle:
    """Minimal article object for Jinja2 template rendering.

    title + summary is capped at _MAX_ENTRY_CHARS total to stay within the
    token budget for corpus-level prompts.
    """

    title: str
    summary: str

    @classmethod
    def from_summary(cls, title: str, summary: str) -> "_TemplateArticle":
        """Build a truncated template article from article fields."""
        combined_len = _MAX_ENTRY_CHARS
        title_trunc = title[:combined_len]
        remaining = combined_len - len(title_trunc) - 3  # " — "
        summary_trunc = summary[:max(0, remaining)] if summary else ""
        return cls(title=title_trunc, summary=summary_trunc)


# ── LLM output schema ─────────────────────────────────────────────────────────


class _EventLLMEntry(BaseModel):
    """A single event entry from the LLM's JSON response."""

    model_config = ConfigDict(extra="ignore")

    event_type: str = ""
    description: str = ""
    detected_date: Any = None
    source_article_indices: list[int] = Field(default_factory=list)


class _EventsLLMOutput(BaseModel):
    """Top-level JSON response from the LLM for events.j2."""

    model_config = ConfigDict(extra="ignore")

    events: list[_EventLLMEntry] = Field(default_factory=list)


# ── Post-processing helpers ───────────────────────────────────────────────────


def _validate_date(value: Any) -> str:
    """Return a valid ISO date string, or '' if invalid or null."""
    if value is None:
        return ""
    s = str(value).strip()
    return s if _ISO_DATE_RE.match(s) else ""


def _deduplicate_events(events: list[ExtractedEvent]) -> list[ExtractedEvent]:
    """Merge events with identical description strings.

    The first occurrence is kept; subsequent occurrences' source_article_indices
    are merged into the first.
    """
    seen: dict[str, list[int]] = {}
    order: list[str] = []

    for event in events:
        if event.description not in seen:
            seen[event.description] = list(event.source_article_indices)
            order.append(event.description)
        else:
            # Merge indices, preserving order, removing duplicates
            existing = seen[event.description]
            for idx in event.source_article_indices:
                if idx not in existing:
                    existing.append(idx)

    # Rebuild ExtractedEvent objects in insertion order
    desc_to_event: dict[str, ExtractedEvent] = {e.description: e for e in events}
    result: list[ExtractedEvent] = []
    for desc in order:
        orig = desc_to_event[desc]
        result.append(
            ExtractedEvent(
                event_type=orig.event_type,
                description=orig.description,
                detected_date=orig.detected_date,
                source_article_indices=seen[desc],
            )
        )
    return result


# ── Step ──────────────────────────────────────────────────────────────────────


class EventExtractor(BasePipelineStep):
    """Extract business events from the article corpus via a single LLM call.

    Attributes:
        name: Step identifier used in logging, metrics, and persistence.
        step_index: Execution order index (7 = seventh step).
        critical: False — event extraction failure is tolerated.
        max_retries: 2 — orchestrator retries the step up to 2 times on
            LLMParseError, appending a corrective hint each time.
    """

    name: str = "EventExtractor"
    step_index: int = 7
    critical: bool = False
    max_retries: int = 2

    def __init__(self, prompt_loader: PromptLoader) -> None:
        self._prompt_loader = prompt_loader

    # ── PipelineStep Protocol ──────────────────────────────────────────────

    def can_execute(self, context: PipelineContext) -> bool:
        """Requires Step 5 (ArticleSummarizer) to have run."""
        return context.outputs.article_summaries is not None

    async def execute(self, context: PipelineContext) -> StepResult:
        """Make a single corpus-level LLM call and extract business events.

        An empty events array from the model is a valid COMPLETE outcome.
        Events with disallowed event_type values are silently discarded.
        Duplicate descriptions are merged by combining source_article_indices.
        """
        summaries = context.outputs.article_summaries or []
        start_ms = int(time.monotonic() * 1000)

        company_info = context.outputs.company_info
        company_name: str = (
            (company_info.name or context.ticker)
            if company_info is not None
            else context.ticker
        )

        logger.info(
            "Starting event extraction",
            extra={"ticker": context.ticker, "article_count": len(summaries)},
        )

        # Build truncated article list for the template (cap at 20)
        template_articles = [
            _TemplateArticle.from_summary(a.title, a.summary)
            for a in summaries[:_MAX_ARTICLES]
        ]

        prompt = self._prompt_loader.render(
            "events.j2",
            ticker=context.ticker,
            company_name=company_name,
            articles=template_articles,
        )

        # Append orchestrator-level retry hint if present
        retry_hint = context.get_llm_retry_hint(self.name)
        if retry_hint:
            prompt += f"\n\n{retry_hint}"

        if estimate_tokens(prompt) > MAX_PROMPT_TOKENS:
            logger.warning(
                "Events prompt exceeds token budget",
                extra={"ticker": context.ticker, "estimated_tokens": estimate_tokens(prompt)},
            )

        raw = await context.llm_provider.complete(
            prompt,
            max_tokens=1000,
            temperature=0.1,
        )

        # extract_json raises LLMParseError if all strategies fail;
        # the orchestrator catches this and retries with a corrective hint.
        parsed = extract_json(raw)

        try:
            llm_output = _EventsLLMOutput.model_validate(parsed)
        except Exception as exc:
            raise LLMParseError(
                f"EventExtractor: failed to validate events schema: {exc}",
                step_name=self.name,
                raw_output=raw,
            ) from exc

        # Post-process events
        valid_events: list[ExtractedEvent] = []
        for entry in llm_output.events:
            # Discard invalid event types
            if entry.event_type not in _ALLOWED_EVENT_TYPES:
                logger.debug(
                    "Discarding event with invalid type",
                    extra={"event_type": entry.event_type},
                )
                continue

            # Discard events with empty description
            if not entry.description.strip():
                continue

            valid_events.append(
                ExtractedEvent(
                    event_type=entry.event_type,
                    description=entry.description.strip(),
                    detected_date=_validate_date(entry.detected_date),
                    source_article_indices=entry.source_article_indices,
                )
            )

        # Deduplicate by description
        deduped = _deduplicate_events(valid_events)

        # Cap at 10 events
        final_events = deduped[:_MAX_EVENTS]

        context.outputs.events = final_events

        duration_ms = int(time.monotonic() * 1000) - start_ms
        event_count = len(final_events)

        logger.info(
            "Event extraction complete",
            extra={
                "event_count": event_count,
                "ticker": context.ticker,
                "duration_ms": duration_ms,
            },
        )

        return StepResult(
            step_name=self.name,
            step_index=self.step_index,
            status=StepStatus.COMPLETE,
            duration_ms=duration_ms,
            output_summary=f"events={event_count}",
        )
