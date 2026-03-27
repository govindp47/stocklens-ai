"""PipelineOrchestrator — sequential step execution with retry, critical branching,
and watchdog timeout support.

Architecture reference: 04_DOMAIN_ENGINE_DESIGN.md § 4 (PipelineOrchestrator algorithm),
§ 9 (concurrency safety rules), § 10 (failure recovery strategy).
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from uuid import UUID

import structlog

from app.domain.exceptions import ExternalProviderError, LLMParseError, TickerNotResolvableError
from app.infrastructure.event_bus import EventBus
from app.infrastructure.providers import LLMProvider
from app.infrastructure.repositories.report_repository import ReportRepository
from app.pipeline.context import PipelineContext
from app.pipeline.steps.base import PipelineStep, StepFailure, StepResult, StepStatus

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


def _now_ms() -> int:
    """Return current monotonic clock value in milliseconds."""
    return time.monotonic_ns() // 1_000_000


class PipelineOrchestrator:
    """Drives the 9-step sequential analysis pipeline for a single run.

    Responsibilities:
    - Order steps by ``step_index`` and call ``can_execute`` before each step.
    - Execute each step via ``_execute_with_retry`` with exponential backoff.
    - Publish a step SSE event after every step outcome (complete / failed / skipped).
    - Fire-and-forget DB upserts for each step (never blocks the pipeline).
    - Halt on critical step failure; continue on non-critical failure.
    - Handle ``asyncio.CancelledError`` (watchdog cancellation) by re-raising
      so the watchdog can do final cleanup.
    - Catch unexpected exceptions at CRITICAL level and mark the run as failed.

    The orchestrator is stateless between runs; all per-run state lives in
    ``PipelineContext``.
    """

    def __init__(
        self,
        steps: list[PipelineStep],
        event_bus: EventBus,
        report_repository: ReportRepository,
        llm_semaphore: asyncio.Semaphore,
    ) -> None:
        # Enforce deterministic ordering regardless of registration order.
        self._steps: list[PipelineStep] = sorted(steps, key=lambda s: s.step_index)
        self._event_bus = event_bus
        self._report_repository = report_repository
        self._llm_semaphore = llm_semaphore  # held by LLMProvider internally (T-025)

    # ──────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────

    async def run(
        self,
        run_id: UUID,
        ticker: str,
        llm_provider: LLMProvider,
    ) -> None:
        """Execute the full analysis pipeline for ``run_id``.

        This coroutine is launched as an ``asyncio.Task`` by ``launch()``.
        All exceptions except ``asyncio.CancelledError`` are caught internally
        so that a pipeline failure never crashes the hosting event loop.

        ``asyncio.CancelledError`` is caught, logged, and **re-raised** so that
        the watchdog (which cancels this task on timeout) can observe the
        cancellation, call ``mark_timed_out``, and publish the timeout event
        before swallowing the error.
        """
        log = logger.bind(run_id=str(run_id), ticker=ticker)

        context = PipelineContext(
            run_id=run_id,
            ticker=ticker,
            llm_provider=llm_provider,
        )

        # ── Mark run as in_progress ────────────────────────────────────────
        try:
            await self._report_repository.mark_in_progress(run_id)
        except Exception:
            # DB failure is non-fatal here; Redis/SSE still tracks progress.
            log.error("Failed to mark run in_progress")

        await self._event_bus.publish(run_id, {
            "type": "pipeline_started",
            "run_id": str(run_id),
            "ticker": ticker,
        })

        steps_completed = 0
        steps_failed = 0
        critical_failure_reason: str | None = None

        try:
            for step in self._steps:
                step_log = log.bind(step_name=step.name, step_index=step.step_index)

                # ── Prerequisites check ────────────────────────────────────
                if not step.can_execute(context):
                    step_log.info("Step skipped — prerequisites not met")
                    asyncio.create_task(
                        self._upsert_step_safe(
                            run_id,
                            StepResult(
                                step_name=step.name,
                                step_index=step.step_index,
                                status=StepStatus.SKIPPED,
                                output_summary="Prerequisites not met",
                            ),
                        )
                    )
                    await self._event_bus.publish(run_id, {
                        "type": "step_update",
                        "step_name": step.name,
                        "step_index": step.step_index,
                        "status": StepStatus.SKIPPED.value,
                        "reason": "Prerequisites not met; step skipped",
                    })
                    continue

                # ── Publish step-started event ─────────────────────────────
                await self._event_bus.publish(run_id, {
                    "type": "step_update",
                    "step_name": step.name,
                    "step_index": step.step_index,
                    "status": StepStatus.RUNNING.value,
                })

                # ── Execute with retry ─────────────────────────────────────
                result = await self._execute_with_retry(step, context)

                # ── Publish step outcome event ─────────────────────────────
                await self._event_bus.publish(run_id, _step_event(result))

                # ── Fire-and-forget DB step upsert ────────────────────────
                asyncio.create_task(self._upsert_step_safe(run_id, result))

                # ── Update counters ────────────────────────────────────────
                if result.status == StepStatus.COMPLETE:
                    steps_completed += 1
                else:
                    steps_failed += 1
                    if step.critical:
                        critical_failure_reason = (
                            f"Critical step '{step.name}' failed: {result.output_summary}"
                        )
                        step_log.warning("Critical step failed — halting pipeline")
                        break

        except asyncio.CancelledError:
            # Watchdog cancelled this task (timeout).  Re-raise so the watchdog
            # coroutine (awaiting this task) can observe the CancelledError,
            # call mark_timed_out, and swallow the exception there.
            log.warning("Pipeline task cancelled by watchdog")
            raise

        except Exception:
            # Programming error — should never reach production.
            log.critical("Unhandled exception in pipeline loop", exc_info=True)
            await self._finalize(
                run_id,
                steps_completed=steps_completed,
                steps_failed=steps_failed,
                error_message="Internal system error",
            )
            return

        # ── Finalize ───────────────────────────────────────────────────────
        await self._finalize(
            run_id,
            steps_completed=steps_completed,
            steps_failed=steps_failed,
            error_message=critical_failure_reason,
            report_json=context.outputs.final_report_json,
        )

    def launch(
        self,
        run_id: UUID,
        ticker: str,
        llm_provider: LLMProvider,
        timeout_seconds: float = 90.0,
    ) -> UUID:
        """Create the pipeline task and a watchdog task; return ``run_id``.

        Both tasks are registered with the running event loop via
        ``asyncio.create_task``.  The watchdog cancels the pipeline task if it
        exceeds ``timeout_seconds``.

        Returns ``run_id`` for convenience so the caller can immediately
        persist or return it without capturing a separate variable.
        """
        pipeline_task: asyncio.Task[None] = asyncio.create_task(
            self.run(run_id, ticker, llm_provider),
            name=f"pipeline-{run_id}",
        )
        asyncio.create_task(
            pipeline_watchdog(
                run_id=run_id,
                pipeline_task=pipeline_task,
                timeout_seconds=timeout_seconds,
                event_bus=self._event_bus,
                report_repository=self._report_repository,
            ),
            name=f"watchdog-{run_id}",
        )
        return run_id

    # ──────────────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────────────

    async def _execute_with_retry(
        self,
        step: PipelineStep,
        context: PipelineContext,
    ) -> StepResult:
        """Execute ``step`` with retry logic.

        Retry behaviour:
        - ``ExternalProviderError(is_retryable=True)``: retry with exponential
          backoff of ``min(2^(attempt-1), 8)`` seconds — [1, 2, 4, 8, 8, …].
        - ``ExternalProviderError(is_retryable=False)``: fail immediately.
        - ``LLMParseError``: store a corrective hint on the context; retry after 1s.
        - Any other exception: propagates up (caught by ``run()``'s outer handler).

        The loop runs at most ``step.max_retries + 1`` times (first attempt plus
        up to ``max_retries`` retries).
        """
        attempt = 0
        last_result: StepResult | None = None

        while attempt <= step.max_retries:
            attempt += 1
            start_ms = _now_ms()

            try:
                result = await step.execute(context)
                duration_ms = _now_ms() - start_ms
                # Overlay the wall-clock duration measured by the orchestrator;
                # the step's own duration_ms (if set) is superseded.
                return StepResult(
                    step_name=result.step_name,
                    step_index=result.step_index,
                    status=result.status,
                    duration_ms=duration_ms,
                    output_summary=result.output_summary,
                )

            except ExternalProviderError as exc:
                duration_ms = _now_ms() - start_ms
                _failure = StepFailure(
                    step_name=step.name,
                    step_index=step.step_index,
                    error_code=exc.error_code,
                    error_message=exc.user_message,
                    retry_count=attempt - 1,
                    is_retryable=exc.is_retryable,
                )
                last_result = StepResult(
                    step_name=step.name,
                    step_index=step.step_index,
                    status=StepStatus.FAILED,
                    duration_ms=duration_ms,
                    output_summary=f"{exc.error_code}: {exc.user_message}",
                )
                if not exc.is_retryable or attempt > step.max_retries:
                    return last_result
                # Retryable: exponential backoff capped at 8 s.
                backoff = min(1 << (attempt - 1), 8)
                await asyncio.sleep(backoff)

            except TickerNotResolvableError as exc:
                duration_ms = _now_ms() - start_ms
                return StepResult(
                    step_name=step.name,
                    step_index=step.step_index,
                    status=StepStatus.FAILED,
                    duration_ms=duration_ms,
                    output_summary=f"TICKER_NOT_RESOLVABLE: {exc}",
                )

            except LLMParseError as exc:
                duration_ms = _now_ms() - start_ms
                # Store corrective hint so the next attempt can adjust the prompt.
                context.set_llm_retry_hint(
                    step.name,
                    "Respond ONLY with valid JSON matching the exact schema. "
                    "Do not include markdown fences or explanatory text.",
                )
                last_result = StepResult(
                    step_name=step.name,
                    step_index=step.step_index,
                    status=StepStatus.FAILED,
                    duration_ms=duration_ms,
                    output_summary=f"LLM_JSON_PARSE_ERROR: step={exc.step_name}",
                )
                if attempt > step.max_retries:
                    return last_result
                await asyncio.sleep(1)

        # Exhausted all attempts (defensive — the logic above should always
        # return inside the loop before reaching here).
        if last_result is None:
            last_result = StepResult(
                step_name=step.name,
                step_index=step.step_index,
                status=StepStatus.FAILED,
                duration_ms=0,
                output_summary="MAX_RETRIES_EXCEEDED",
            )
        return last_result

    async def _finalize(
        self,
        run_id: UUID,
        *,
        steps_completed: int,
        steps_failed: int,
        error_message: str | None = None,
        report_json: str | None = None,
    ) -> None:
        """Persist the final run state and publish the terminal pipeline event.

        If ``error_message`` is set the run is marked failed; otherwise complete.
        ``report_json`` is the serialised AnalysisReport from ReportAssembler;
        falls back to an empty JSON object if the assembler did not run.
        DB write failures are logged but do not prevent the SSE event from being
        published (clients receive data regardless of DB persistence).
        """
        log = logger.bind(run_id=str(run_id))

        if error_message is not None:
            try:
                await self._report_repository.mark_failed(
                    run_id,
                    error_message,
                    steps_completed,
                    steps_failed,
                )
            except Exception:
                log.error("Failed to persist pipeline failure to DB")
            await self._event_bus.publish(run_id, {
                "type": "pipeline_failed",
                "run_id": str(run_id),
                "reason": error_message,
                "steps_completed": steps_completed,
                "steps_failed": steps_failed,
            })
        else:
            persisted_json = report_json if report_json is not None else json.dumps({})
            try:
                await self._report_repository.mark_complete(
                    run_id,
                    persisted_json,
                    steps_completed,
                )
            except Exception:
                log.error("Failed to persist pipeline completion to DB")
            await self._event_bus.publish(run_id, {
                "type": "pipeline_complete",
                "run_id": str(run_id),
                "steps_completed": steps_completed,
            })

    async def _upsert_step_safe(self, run_id: UUID, result: StepResult) -> None:
        """Fire-and-forget step DB upsert; logs but never propagates failures."""
        try:
            await self._report_repository.upsert_step(
                run_id,
                result.step_index,
                result.step_name,
                result.status.value,
                duration_ms=result.duration_ms,
                output_summary=(
                    {"summary": result.output_summary} if result.output_summary else None
                ),
            )
        except Exception:
            logger.error(
                "Fire-and-forget upsert_step failed",
                run_id=str(run_id),
                step_name=result.step_name,
            )


# ──────────────────────────────────────────────────────────────────────────────
# Watchdog (T-018)
# ──────────────────────────────────────────────────────────────────────────────


async def pipeline_watchdog(
    run_id: UUID,
    pipeline_task: asyncio.Task[None],
    timeout_seconds: float,
    event_bus: EventBus,
    report_repository: ReportRepository,
) -> None:
    """Cancel a pipeline task that exceeds ``timeout_seconds``.

    Mechanism:
    1. ``asyncio.wait_for(asyncio.shield(pipeline_task), timeout)`` waits for
       the pipeline to complete without holding a cancellation handle on it.
       When the timeout fires, ``wait_for`` cancels the *shield* (not the task)
       and raises ``asyncio.TimeoutError``.
    2. On ``TimeoutError``, the watchdog explicitly cancels the pipeline task
       via ``task.cancel()``, then awaits the task to let it finish its
       ``CancelledError`` handling and re-raise.
    3. The watchdog catches and **swallows** the ``CancelledError`` propagated
       by the re-raise in ``PipelineOrchestrator.run()``.
    4. ``mark_timed_out`` is called **exactly once** here (run() does not call
       it — it only re-raises CancelledError to signal the watchdog).
    5. The terminal ``pipeline_timeout`` SSE event is published after the DB
       write so clients receive it.

    If the pipeline completes before the timeout, ``wait_for`` returns normally
    and this function exits without calling ``mark_timed_out``.
    """
    log = logger.bind(run_id=str(run_id), timeout_seconds=timeout_seconds)

    try:
        # asyncio.shield prevents wait_for from cancelling the pipeline task
        # when its internal timeout fires — we want to control cancellation.
        await asyncio.wait_for(asyncio.shield(pipeline_task), timeout=timeout_seconds)
        # Pipeline completed within the timeout window — nothing to do.
        log.debug("Pipeline completed before watchdog timeout")

    except asyncio.TimeoutError:
        log.warning("Pipeline watchdog fired — cancelling pipeline task")

        # Explicitly cancel the pipeline task now that we know it timed out.
        pipeline_task.cancel()

        try:
            # Await completion so the event loop can process the CancelledError
            # inside run() (logging + re-raise) before we proceed with cleanup.
            await pipeline_task
        except asyncio.CancelledError:
            # Expected: run() re-raises CancelledError after catching it.
            pass
        except Exception:
            # Defensive: run() should catch everything else internally.
            log.error("Unexpected exception while awaiting cancelled pipeline task")

        # ── Cleanup — called exactly once per timeout ──────────────────────
        try:
            await report_repository.mark_timed_out(run_id)
        except Exception:
            log.error("Failed to mark run timed_out after watchdog cancellation")

        await event_bus.publish(run_id, {
            "type": "pipeline_timeout",
            "run_id": str(run_id),
        })
        # CancelledError is NOT re-raised here — watchdog swallows it.

    except Exception:
        # Defensive: pipeline_task raised an unexpected exception (shouldn't
        # happen since run() catches everything internally).
        log.error("Unexpected exception in pipeline_watchdog", exc_info=True)


# ──────────────────────────────────────────────────────────────────────────────
# Module-level helpers
# ──────────────────────────────────────────────────────────────────────────────


def _step_event(result: StepResult) -> dict[str, Any]:
    """Build the SSE event dict for a completed or failed step."""
    return {
        "type": "step_update",
        "step_name": result.step_name,
        "step_index": result.step_index,
        "status": result.status.value,
        "duration_ms": result.duration_ms,
        "output_summary": result.output_summary,
    }
