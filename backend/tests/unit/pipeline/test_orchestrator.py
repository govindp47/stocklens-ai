"""Unit tests for PipelineOrchestrator and pipeline_watchdog.

All tests use in-process fakes (AsyncMock repository, AsyncMock event bus)
and MockStep objects — no external services required.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.domain.exceptions import ExternalProviderError, LLMParseError
from app.infrastructure.repositories.report_repository import ReportRepository
from app.pipeline.context import PipelineContext
from app.pipeline.orchestrator import PipelineOrchestrator, pipeline_watchdog
from app.pipeline.steps.base import StepResult, StepStatus

# ──────────────────────────────────────────────────────────────────────────────
# Test helpers
# ──────────────────────────────────────────────────────────────────────────────


class MockStep:
    """Minimal PipelineStep-compatible class for orchestrator tests.

    ``outcomes`` is a list of values executed in order:
      - ``StepStatus`` value  → returned as StepResult with that status
      - ``BaseException`` instance → raised (simulates ExternalProviderError etc.)
    When the list is exhausted, the last element is repeated.
    """

    def __init__(
        self,
        name: str,
        step_index: int,
        *,
        critical: bool = False,
        max_retries: int = 0,
        outcomes: list[StepStatus | BaseException] | None = None,
        can_exec: bool = True,
    ) -> None:
        self.name = name
        self.step_index = step_index
        self.critical = critical
        self.max_retries = max_retries
        self._outcomes: list[StepStatus | BaseException] = outcomes or [StepStatus.COMPLETE]
        self._outcome_index = 0
        self._can_exec = can_exec
        self.execute_count = 0

    def can_execute(self, context: PipelineContext) -> bool:
        return self._can_exec

    async def execute(self, context: PipelineContext) -> StepResult:
        self.execute_count += 1
        idx = min(self._outcome_index, len(self._outcomes) - 1)
        outcome = self._outcomes[idx]
        self._outcome_index += 1

        if isinstance(outcome, BaseException):
            raise outcome
        return StepResult(
            step_name=self.name,
            step_index=self.step_index,
            status=outcome,
            output_summary="ok",
        )


def _make_orchestrator(
    steps: list[MockStep],
    repo: AsyncMock,
    event_bus: AsyncMock,
) -> PipelineOrchestrator:
    return PipelineOrchestrator(
        steps=steps,  # type: ignore[arg-type]
        event_bus=event_bus,
        report_repository=repo,
        llm_semaphore=asyncio.Semaphore(3),
    )


def _mock_repo() -> AsyncMock:
    return AsyncMock(spec=ReportRepository)


def _mock_bus() -> AsyncMock:
    return AsyncMock()


def _published_types(event_bus: AsyncMock) -> list[str]:
    """Extract the 'type' field from every event_bus.publish call."""
    return [c.args[1].get("type", "") for c in event_bus.publish.call_args_list]


# ──────────────────────────────────────────────────────────────────────────────
# Happy path
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit()
async def test_complete_pipeline_happy_path() -> None:
    repo, bus = _mock_repo(), _mock_bus()
    run_id = uuid4()
    steps = [MockStep("a", 1), MockStep("b", 2), MockStep("c", 3)]

    await _make_orchestrator(steps, repo, bus).run(run_id, "AAPL", MagicMock())
    await asyncio.sleep(0)  # drain fire-and-forget upsert tasks

    repo.mark_in_progress.assert_awaited_once_with(run_id)
    repo.mark_complete.assert_awaited_once()
    for step in steps:
        assert step.execute_count == 1

    types = _published_types(bus)
    assert "pipeline_started" in types
    assert "pipeline_complete" in types


@pytest.mark.unit()
async def test_steps_executed_in_step_index_order() -> None:
    """Orchestrator must sort steps by step_index regardless of registration order."""
    repo, bus = _mock_repo(), _mock_bus()
    execution_order: list[str] = []

    class OrderedStep(MockStep):
        async def execute(self, context: PipelineContext) -> StepResult:
            execution_order.append(self.name)
            return await super().execute(context)

    steps = [OrderedStep("third", 3), OrderedStep("first", 1), OrderedStep("second", 2)]
    await _make_orchestrator(steps, repo, bus).run(uuid4(), "AAPL", MagicMock())

    assert execution_order == ["first", "second", "third"]


# ──────────────────────────────────────────────────────────────────────────────
# Critical step failure
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit()
async def test_critical_step_failure_halts_pipeline() -> None:
    repo, bus = _mock_repo(), _mock_bus()
    step1 = MockStep("ticker_validator", 1, critical=True, outcomes=[StepStatus.FAILED])
    step2 = MockStep("market_data", 2)
    step3 = MockStep("news", 3)

    await _make_orchestrator([step1, step2, step3], repo, bus).run(uuid4(), "INVALID", MagicMock())
    await asyncio.sleep(0)

    repo.mark_failed.assert_awaited_once()
    repo.mark_complete.assert_not_awaited()
    assert step2.execute_count == 0, "Step 2 must not execute after critical failure"
    assert step3.execute_count == 0, "Step 3 must not execute after critical failure"

    types = _published_types(bus)
    assert "pipeline_failed" in types


# ──────────────────────────────────────────────────────────────────────────────
# Non-critical step failure
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit()
async def test_non_critical_failure_continues() -> None:
    repo, bus = _mock_repo(), _mock_bus()
    step1 = MockStep("market_data", 1, critical=False, outcomes=[StepStatus.FAILED])
    step2 = MockStep("news", 2)
    step3 = MockStep("dedup", 3)

    await _make_orchestrator([step1, step2, step3], repo, bus).run(uuid4(), "AAPL", MagicMock())
    await asyncio.sleep(0)

    repo.mark_complete.assert_awaited_once()
    assert step2.execute_count == 1
    assert step3.execute_count == 1


# ──────────────────────────────────────────────────────────────────────────────
# can_execute — step skipping
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit()
async def test_step_skipped_when_can_execute_false() -> None:
    repo, bus = _mock_repo(), _mock_bus()
    step1 = MockStep("a", 1)
    step2 = MockStep("b", 2, can_exec=False)  # skipped
    step3 = MockStep("c", 3)

    await _make_orchestrator([step1, step2, step3], repo, bus).run(uuid4(), "AAPL", MagicMock())
    await asyncio.sleep(0)

    assert step1.execute_count == 1
    assert step2.execute_count == 0
    assert step3.execute_count == 1
    repo.mark_complete.assert_awaited_once()

    skipped_events = [
        c.args[1]
        for c in bus.publish.call_args_list
        if c.args[1].get("status") == StepStatus.SKIPPED.value
    ]
    assert len(skipped_events) == 1
    assert skipped_events[0]["step_name"] == "b"


# ──────────────────────────────────────────────────────────────────────────────
# Retry logic — ExternalProviderError
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit()
async def test_retry_fires_on_retryable_error() -> None:
    repo, bus = _mock_repo(), _mock_bus()
    retryable = ExternalProviderError(
        "provider down",
        error_code="PROVIDER_DOWN",
        user_message="Provider temporarily unavailable",
        is_retryable=True,
    )
    step = MockStep("market_data", 1, max_retries=1, outcomes=[retryable, StepStatus.COMPLETE])

    with patch("asyncio.sleep", new_callable=AsyncMock):
        await _make_orchestrator([step], repo, bus).run(uuid4(), "AAPL", MagicMock())

    assert step.execute_count == 2  # initial attempt + 1 retry
    repo.mark_complete.assert_awaited_once()


@pytest.mark.unit()
async def test_no_retry_on_non_retryable_error() -> None:
    repo, bus = _mock_repo(), _mock_bus()
    non_retryable = ExternalProviderError(
        "ticker unknown",
        error_code="TICKER_NOT_RESOLVABLE",
        user_message="Ticker not found",
        is_retryable=False,
    )
    step = MockStep(
        "ticker_validator",
        1,
        critical=True,
        max_retries=1,
        outcomes=[non_retryable, StepStatus.COMPLETE],
    )

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await _make_orchestrator([step], repo, bus).run(uuid4(), "INVALID", MagicMock())

    assert step.execute_count == 1  # no retry for non-retryable
    mock_sleep.assert_not_awaited()
    repo.mark_failed.assert_awaited_once()


@pytest.mark.unit()
async def test_retry_exhaustion_marks_step_failed() -> None:
    """If all retry attempts fail, the final StepResult must be FAILED."""
    repo, bus = _mock_repo(), _mock_bus()
    retryable = ExternalProviderError(
        "still down",
        error_code="PROVIDER_DOWN",
        user_message="Still unavailable",
        is_retryable=True,
    )
    step = MockStep(
        "market_data",
        1,
        critical=False,
        max_retries=1,
        outcomes=[retryable, retryable],  # both attempts fail
    )

    with patch("asyncio.sleep", new_callable=AsyncMock):
        await _make_orchestrator([step], repo, bus).run(uuid4(), "AAPL", MagicMock())

    assert step.execute_count == 2  # max_retries=1 → 2 total attempts
    # Non-critical, so pipeline still completes
    repo.mark_complete.assert_awaited_once()

    failed_events = [
        c.args[1]
        for c in bus.publish.call_args_list
        if c.args[1].get("status") == StepStatus.FAILED.value
    ]
    assert len(failed_events) == 1


# ──────────────────────────────────────────────────────────────────────────────
# Retry logic — LLMParseError
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit()
async def test_llm_parse_error_stores_hint_and_retries() -> None:
    """LLMParseError must store a corrective hint on the context and retry."""
    repo, bus = _mock_repo(), _mock_bus()
    captured: list[str | None] = []

    class HintCapturingStep(MockStep):
        async def execute(self, context: PipelineContext) -> StepResult:
            captured.append(context.get_llm_retry_hint(self.name))
            return await super().execute(context)

    parse_err = LLMParseError("bad json", step_name="llm_step", raw_output="{bad}")
    step = HintCapturingStep(
        "llm_step", 1, max_retries=1, outcomes=[parse_err, StepStatus.COMPLETE]
    )

    with patch("asyncio.sleep", new_callable=AsyncMock):
        await _make_orchestrator([step], repo, bus).run(uuid4(), "AAPL", MagicMock())

    assert len(captured) == 2
    assert captured[0] is None, "First attempt must not have a hint"
    assert captured[1] is not None, "Second attempt must find the corrective hint"
    repo.mark_complete.assert_awaited_once()


# ──────────────────────────────────────────────────────────────────────────────
# Exponential backoff sequence
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit()
async def test_exponential_backoff_sequence() -> None:
    """Backoff delays must follow [1, 2, 4, 8, 8, …] seconds capped at 8."""
    repo, bus = _mock_repo(), _mock_bus()
    retryable = ExternalProviderError(
        "down", error_code="DOWN", user_message="down", is_retryable=True
    )
    # 3 retries so we get delays after attempts 1, 2, 3
    step = MockStep(
        "step",
        1,
        critical=False,
        max_retries=3,
        outcomes=[retryable, retryable, retryable, StepStatus.COMPLETE],
    )

    sleep_calls: list[Any] = []

    async def capture_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    with patch("asyncio.sleep", side_effect=capture_sleep):
        await _make_orchestrator([step], repo, bus).run(uuid4(), "AAPL", MagicMock())

    # Backoff after attempt 1 → 1s, attempt 2 → 2s, attempt 3 → 4s
    assert sleep_calls == [1, 2, 4]
    assert step.execute_count == 4


@pytest.mark.unit()
async def test_exponential_backoff_capped_at_8s() -> None:
    """Backoff must not exceed 8 seconds regardless of retry count."""
    repo, bus = _mock_repo(), _mock_bus()
    retryable = ExternalProviderError(
        "down", error_code="DOWN", user_message="down", is_retryable=True
    )
    # 5 retries → delays after attempts 1-5; cap kicks in at attempt 4+
    step = MockStep(
        "step",
        1,
        critical=False,
        max_retries=5,
        outcomes=[retryable] * 5 + [StepStatus.COMPLETE],
    )

    sleep_calls: list[Any] = []

    async def capture_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    with patch("asyncio.sleep", side_effect=capture_sleep):
        await _make_orchestrator([step], repo, bus).run(uuid4(), "AAPL", MagicMock())

    assert sleep_calls == [1, 2, 4, 8, 8]
    assert max(sleep_calls) == 8


# ──────────────────────────────────────────────────────────────────────────────
# Watchdog
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit()
async def test_watchdog_cancels_slow_pipeline() -> None:
    """Watchdog must cancel a pipeline that exceeds the timeout and call mark_timed_out."""
    repo, bus = _mock_repo(), _mock_bus()
    run_id = uuid4()

    async def slow_pipeline() -> None:
        try:
            await asyncio.sleep(100)
        except asyncio.CancelledError:
            raise  # simulate orchestrator.run() re-raising

    task: asyncio.Task[None] = asyncio.create_task(slow_pipeline())

    await pipeline_watchdog(
        run_id=run_id,
        pipeline_task=task,
        timeout_seconds=0.05,
        event_bus=bus,
        report_repository=repo,
    )

    repo.mark_timed_out.assert_awaited_once_with(run_id)
    assert task.done()

    types = _published_types(bus)
    assert "pipeline_timeout" in types


@pytest.mark.unit()
async def test_watchdog_does_not_cancel_fast_pipeline() -> None:
    """Watchdog must NOT call mark_timed_out if the pipeline completes before timeout."""
    repo, bus = _mock_repo(), _mock_bus()
    run_id = uuid4()

    async def fast_pipeline() -> None:
        await asyncio.sleep(0)

    task: asyncio.Task[None] = asyncio.create_task(fast_pipeline())

    await pipeline_watchdog(
        run_id=run_id,
        pipeline_task=task,
        timeout_seconds=5.0,
        event_bus=bus,
        report_repository=repo,
    )

    repo.mark_timed_out.assert_not_awaited()


@pytest.mark.unit()
async def test_watchdog_swallows_cancelled_error() -> None:
    """pipeline_watchdog must not propagate CancelledError to its caller."""
    repo, bus = _mock_repo(), _mock_bus()

    async def slow_pipeline() -> None:
        await asyncio.sleep(100)

    task: asyncio.Task[None] = asyncio.create_task(slow_pipeline())

    # If CancelledError leaked, pytest would fail this test automatically.
    await pipeline_watchdog(
        run_id=uuid4(),
        pipeline_task=task,
        timeout_seconds=0.05,
        event_bus=bus,
        report_repository=repo,
    )
    # No exception raised → test passes


@pytest.mark.unit()
async def test_launch_creates_pipeline_and_watchdog_tasks() -> None:
    """launch() must return run_id and schedule both pipeline and watchdog tasks."""
    repo, bus = _mock_repo(), _mock_bus()
    run_id = uuid4()
    step = MockStep("a", 1)

    orch = _make_orchestrator([step], repo, bus)
    returned_id = orch.launch(run_id, "AAPL", MagicMock(), timeout_seconds=30.0)

    assert returned_id == run_id

    # Let the event loop process the created tasks.
    await asyncio.sleep(0.01)
    repo.mark_in_progress.assert_awaited_once_with(run_id)
