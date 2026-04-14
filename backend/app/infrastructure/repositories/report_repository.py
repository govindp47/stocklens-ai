"""ReportRepository — SQL operations for analysis_runs and pipeline_steps.

All queries use asyncpg parameterized syntax ($1, $2, ...).
No f-string interpolation of user-supplied values is used anywhere.

Status transition methods implement optimistic locking via WHERE status = ...
guards; they return True if the transition succeeded (rowcount == 1) and False
if it did not (a concurrent transition already moved the row to another state).

All asyncpg.PostgresError exceptions are caught and re-raised as
ExternalProviderError so callers never receive raw database exceptions.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

import asyncpg

from app.domain.exceptions import ExternalProviderError

logger = logging.getLogger(__name__)


class ReportRepository:
    """Data-access object for analysis run and pipeline step persistence."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    # ──────────────────────────────────────────────────────────────────────
    # Run lifecycle
    # ──────────────────────────────────────────────────────────────────────

    async def create_run(
        self,
        run_id: UUID,
        ticker: str,
        ip_address: str | None,
        llm_provider: str,
        llm_model: str | None,
    ) -> None:
        """Insert a new analysis run in 'accepted' status.

        steps_total is fixed at 9 (the full pipeline step count).
        """
        sql = """
            INSERT INTO analysis_runs
                (run_id, ticker, ip_address, llm_provider, llm_model,
                 status, steps_total, steps_completed, steps_failed)
            VALUES
                ($1, $2, $3, $4, $5,
                 'accepted', 9, 0, 0)
        """
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(sql, run_id, ticker, ip_address, llm_provider, llm_model)
        except asyncpg.PostgresError as exc:
            raise ExternalProviderError(
                f"Failed to create run {run_id}: {exc}",
                error_code="DB_CREATE_RUN_ERROR",
                user_message="Failed to register analysis run.",
                is_retryable=False,
            ) from exc

    async def mark_in_progress(self, run_id: UUID) -> bool:
        """Transition run status from 'accepted' → 'in_progress'.

        Returns True if the transition succeeded (exactly one row updated).
        Returns False if the run is already in another state (optimistic lock).
        """
        sql = """
            UPDATE analysis_runs
            SET    status     = 'in_progress',
                   started_at = NOW()
            WHERE  run_id = $1
              AND  status  = 'accepted'
        """
        try:
            async with self._pool.acquire() as conn:
                result = await conn.execute(sql, run_id)
            return self._rowcount(result) > 0
        except asyncpg.PostgresError as exc:
            raise ExternalProviderError(
                f"Failed to mark run {run_id} in_progress: {exc}",
                error_code="DB_STATUS_TRANSITION_ERROR",
                user_message="Failed to update run status.",
                is_retryable=True,
            ) from exc

    async def mark_complete(
        self,
        run_id: UUID,
        report_data_json: str,
        steps_completed: int,
    ) -> bool:
        """Transition run status from 'in_progress' → 'complete'.

        The AND report_data IS NULL guard prevents a double-write race condition:
        if report_data has already been set (by a concurrent transition), this
        UPDATE will match zero rows and return False.

        Returns True on success, False if the guard rejected the update.
        """
        sql = """
            UPDATE analysis_runs
            SET    status          = 'complete',
                   completed_at    = NOW(),
                   duration_ms     = EXTRACT(EPOCH FROM (NOW() - started_at))::INTEGER * 1000,
                   report_data     = $2::jsonb,
                   steps_completed = $3
            WHERE  run_id      = $1
              AND  status      = 'in_progress'
              AND  report_data IS NULL
        """
        try:
            async with self._pool.acquire() as conn:
                result = await conn.execute(sql, run_id, report_data_json, steps_completed)
            return self._rowcount(result) > 0
        except asyncpg.PostgresError as exc:
            raise ExternalProviderError(
                f"Failed to mark run {run_id} complete: {exc}",
                error_code="DB_STATUS_TRANSITION_ERROR",
                user_message="Failed to save analysis result.",
                is_retryable=False,
            ) from exc

    async def mark_failed(
        self,
        run_id: UUID,
        error_message: str,
        steps_completed: int,
        steps_failed: int,
    ) -> bool:
        """Transition run status to 'failed' from 'accepted' or 'in_progress'.

        Returns True if the transition succeeded.
        """
        sql = """
            UPDATE analysis_runs
            SET    status          = 'failed',
                   completed_at    = NOW(),
                   error_message   = $2,
                   steps_completed = $3,
                   steps_failed    = $4
            WHERE  run_id = $1
              AND  status IN ('accepted', 'in_progress')
        """
        try:
            async with self._pool.acquire() as conn:
                result = await conn.execute(
                    sql, run_id, error_message, steps_completed, steps_failed
                )
            return self._rowcount(result) > 0
        except asyncpg.PostgresError as exc:
            raise ExternalProviderError(
                f"Failed to mark run {run_id} failed: {exc}",
                error_code="DB_STATUS_TRANSITION_ERROR",
                user_message="Failed to record run failure.",
                is_retryable=True,
            ) from exc

    async def mark_timed_out(self, run_id: UUID) -> bool:
        """Transition run status to 'timed_out' from 'accepted' or 'in_progress'.

        Returns True if the transition succeeded.
        """
        sql = """
            UPDATE analysis_runs
            SET    status       = 'timed_out',
                   completed_at = NOW()
            WHERE  run_id = $1
              AND  status IN ('accepted', 'in_progress')
        """
        try:
            async with self._pool.acquire() as conn:
                result = await conn.execute(sql, run_id)
            return self._rowcount(result) > 0
        except asyncpg.PostgresError as exc:
            raise ExternalProviderError(
                f"Failed to mark run {run_id} timed_out: {exc}",
                error_code="DB_STATUS_TRANSITION_ERROR",
                user_message="Failed to record run timeout.",
                is_retryable=True,
            ) from exc

    # ──────────────────────────────────────────────────────────────────────
    # Pipeline step persistence
    # ──────────────────────────────────────────────────────────────────────

    async def upsert_step(
        self,
        run_id: UUID,
        step_index: int,
        step_name: str,
        status: str,
        *,
        duration_ms: int | None = None,
        input_summary: dict[str, Any] | None = None,
        output_summary: dict[str, Any] | None = None,
        error_message: str | None = None,
        error_code: str | None = None,
        retry_count: int = 0,
    ) -> None:
        """Insert or update a pipeline step record.

        The UNIQUE constraint (run_id, step_index) makes ON CONFLICT idempotent:
        calling this method twice with the same (run_id, step_index) updates the
        existing row rather than raising a duplicate-key error.

        started_at is set on first insert; completed_at is set when status is
        'complete', 'failed', or 'skipped'.
        """
        terminal_statuses = ("complete", "failed", "skipped")
        input_json = json.dumps(input_summary) if input_summary is not None else None
        output_json = json.dumps(output_summary) if output_summary is not None else None

        sql = """
            INSERT INTO pipeline_steps
                (run_id, step_index, step_name, status,
                 started_at, completed_at, duration_ms,
                 input_summary, output_summary,
                 error_message, error_code, retry_count)
            VALUES
                ($1, $2, $3, $4::text,
                 NOW(),
                 CASE WHEN $4::text = ANY($5::text[]) THEN NOW() ELSE NULL END,
                 $6,
                 $7::jsonb,
                 $8::jsonb,
                 $9, $10, $11)
            ON CONFLICT (run_id, step_index)
            DO UPDATE SET
                status         = EXCLUDED.status,
                completed_at   = CASE
                    WHEN EXCLUDED.status = ANY($5::text[]) THEN NOW()
                    ELSE pipeline_steps.completed_at
                END,
                duration_ms    = COALESCE(EXCLUDED.duration_ms, pipeline_steps.duration_ms),
                output_summary = COALESCE(EXCLUDED.output_summary, pipeline_steps.output_summary),
                error_message  = COALESCE(EXCLUDED.error_message, pipeline_steps.error_message),
                error_code     = COALESCE(EXCLUDED.error_code, pipeline_steps.error_code),
                retry_count    = EXCLUDED.retry_count
        """
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    sql,
                    run_id,
                    step_index,
                    step_name,
                    status,
                    list(terminal_statuses),
                    duration_ms,
                    input_json,
                    output_json,
                    error_message,
                    error_code,
                    retry_count,
                )
        except asyncpg.PostgresError as exc:
            raise ExternalProviderError(
                f"Failed to upsert step {step_name} for run {run_id}: {exc}",
                error_code="DB_UPSERT_STEP_ERROR",
                user_message="Failed to record pipeline step.",
                is_retryable=True,
            ) from exc

    # ──────────────────────────────────────────────────────────────────────
    # Read operations
    # ──────────────────────────────────────────────────────────────────────

    async def get_run_by_id(self, run_id: UUID) -> dict[str, Any] | None:
        """Return the analysis_runs row for run_id, or None if not found.

        Excludes soft-deleted rows (is_deleted = TRUE).
        """
        sql = """
            SELECT
                run_id, ticker, status, created_at, started_at,
                completed_at, updated_at, duration_ms,
                llm_provider, llm_model, report_data,
                error_message, steps_total, steps_completed, steps_failed
            FROM  analysis_runs
            WHERE run_id     = $1
              AND is_deleted = FALSE
        """
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(sql, run_id)
            if row is None:
                return None
            return dict(row)
        except asyncpg.PostgresError as exc:
            raise ExternalProviderError(
                f"Failed to fetch run {run_id}: {exc}",
                error_code="DB_FETCH_RUN_ERROR",
                user_message="Failed to retrieve analysis result.",
                is_retryable=True,
            ) from exc

    async def get_completed_runs(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Return completed analysis runs ordered by completion time descending.

        Excludes soft-deleted rows. Returns metadata columns only (no report_data).
        """
        sql = """
            SELECT
                run_id, ticker, status, created_at, completed_at,
                duration_ms, llm_provider, llm_model,
                steps_total, steps_completed, steps_failed
            FROM  analysis_runs
            WHERE status     = 'complete'
              AND is_deleted = FALSE
            ORDER BY completed_at DESC
            LIMIT  $1
            OFFSET $2
        """
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(sql, limit, offset)
            return [dict(row) for row in rows]
        except asyncpg.PostgresError as exc:
            raise ExternalProviderError(
                f"Failed to list completed runs: {exc}",
                error_code="DB_LIST_RUNS_ERROR",
                user_message="Failed to retrieve completed runs.",
                is_retryable=True,
            ) from exc

    async def get_recent_run_for_ip_and_ticker(
        self,
        ip_address: str,
        ticker: str,
    ) -> UUID | None:
        """Return the run_id of a recent accepted/in_progress run for this IP + ticker.

        Implements the 2-minute idempotency window: if the same IP submits the
        same ticker within 2 minutes of a prior run, return the existing run_id
        so the caller can subscribe to its SSE stream instead of spawning a new run.

        Returns None if no matching recent run exists.
        """
        sql = """
            SELECT run_id
            FROM   analysis_runs
            WHERE  ip_address  = $1
              AND  ticker      = $2
              AND  status      IN ('accepted', 'in_progress')
              AND  created_at  > NOW() - INTERVAL '2 minutes'
              AND  is_deleted  = FALSE
            ORDER BY created_at DESC
            LIMIT 1
        """
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(sql, ip_address, ticker)
            if row is None:
                return None
            return UUID(str(row["run_id"]))
        except asyncpg.PostgresError as exc:
            raise ExternalProviderError(
                f"Failed to check idempotency for {ip_address}/{ticker}: {exc}",
                error_code="DB_IDEMPOTENCY_CHECK_ERROR",
                user_message="Failed to check for existing run.",
                is_retryable=True,
            ) from exc

    # ──────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _rowcount(result: str) -> int:
        """Parse the rowcount from asyncpg's command status string.

        asyncpg returns a string like 'UPDATE 1' or 'DELETE 0'.
        """
        try:
            return int(result.split()[-1])
        except (ValueError, IndexError):
            return 0
