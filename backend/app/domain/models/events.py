"""Business event extraction domain models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ExtractedEvent(BaseModel):
    """A single business event detected by the LLM from the article corpus."""

    model_config = ConfigDict(frozen=True)

    event_type: str  # e.g. "earnings", "acquisition", "leadership_change"
    description: str
    detected_date: str  # ISO 8601: YYYY-MM-DD
    source_article_indices: list[int] = []


class EventsResult(BaseModel):
    """All business events extracted for a pipeline run."""

    model_config = ConfigDict(frozen=True)

    available: bool = False
    events: list[ExtractedEvent] = []
