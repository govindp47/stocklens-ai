"""SSE event Pydantic models for the pipeline event stream.

Every event published through RedisEventBus conforms to one of these models.
The ``event_type`` field is the discriminator used by the SSE router to route
events to the correct serialiser and to filter events for reconnecting clients.

Architecture reference: 01_SYSTEM_ARCHITECTURE.md (SSE and Redis Pub/Sub pattern).
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class _BaseEvent(BaseModel):
    """Common fields shared by all pipeline events."""

    model_config = ConfigDict(frozen=True)

    run_id: UUID


class StepEvent(_BaseEvent):
    """Emitted after every step outcome (running / complete / failed / skipped)."""

    event_type: Literal["step_event"] = "step_event"
    step_name: str
    step_index: int
    status: str  # StepStatus.value — stored as string for transport
    duration_ms: int = 0
    reason: str | None = None  # populated on failure or skip


class PipelineCompleteEvent(_BaseEvent):
    """Emitted when the orchestrator finishes all steps successfully."""

    event_type: Literal["pipeline_complete"] = "pipeline_complete"
    steps_completed: int


class PipelineFailedEvent(_BaseEvent):
    """Emitted when a critical step failure halts the pipeline, or on internal error."""

    event_type: Literal["pipeline_failed"] = "pipeline_failed"
    reason: str
    failed_step: str | None = None
    failed_step_is_critical: bool = False
    steps_completed: int = 0
    steps_failed: int = 0


class PipelineTimeoutEvent(_BaseEvent):
    """Emitted by the watchdog when the pipeline exceeds the timeout budget."""

    event_type: Literal["pipeline_timeout"] = "pipeline_timeout"


class PipelineStartedEvent(_BaseEvent):
    """Emitted at the very start of the pipeline run."""

    event_type: Literal["pipeline_started"] = "pipeline_started"
    ticker: str


# Discriminated union — useful for SSE router deserialization.
PipelineEvent = (
    StepEvent
    | PipelineCompleteEvent
    | PipelineFailedEvent
    | PipelineTimeoutEvent
    | PipelineStartedEvent
)

# Event types that signal the pipeline has ended (used for sentinel key logic).
TERMINAL_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "pipeline_complete",
        "pipeline_failed",
        "pipeline_timeout",
    }
)
