"""Pipeline step base definitions: StepStatus, StepResult, StepFailure, PipelineStep."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.pipeline.context import PipelineContext


class StepStatus(str, Enum):
    """Lifecycle states for a pipeline step.

    String values are persisted to the database — do not rename.
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class StepResult:
    """Immutable record of a successfully completed (or skipped) step."""

    step_name: str
    step_index: int
    status: StepStatus
    duration_ms: int = 0
    output_summary: str = ""


@dataclass(frozen=True)
class StepFailure:
    """Immutable record of a failed step execution."""

    step_name: str
    step_index: int
    error_code: str
    error_message: str
    retry_count: int
    is_retryable: bool
    status: StepStatus = field(default=StepStatus.FAILED)


@runtime_checkable
class PipelineStep(Protocol):
    """Structural interface that every pipeline step must satisfy.

    The orchestrator (T-017) drives execution through this Protocol.
    Concrete steps should extend ``BasePipelineStep`` to inherit the
    default ``can_execute`` implementation; steps with non-trivial
    prerequisites override it.
    """

    name: str
    step_index: int
    critical: bool          # if True, failure halts the entire pipeline
    max_retries: int        # 0 = no retry; ≥1 = retry on retryable failure

    async def execute(self, context: PipelineContext) -> StepResult:
        """Run the step logic and return a StepResult."""
        ...

    def can_execute(self, context: PipelineContext) -> bool:
        """Return True if this step's prerequisites are satisfied.

        The orchestrator calls this before executing; if False the step is
        recorded as SKIPPED and execution continues with the next step.
        """
        ...


class BasePipelineStep:
    """Concrete base class providing a default ``can_execute`` implementation.

    Extend this class for steps that have no prerequisites (the common case).
    Steps with prerequisites override ``can_execute`` to inspect
    ``context.outputs``.
    """

    def can_execute(self, context: PipelineContext) -> bool:  # noqa: ARG002
        """Default: always executable."""
        return True
