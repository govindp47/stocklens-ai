"""GET /api/v1/runs — list successfully completed analysis runs.

Returns a paginated list of completed runs with metadata (ticker, completion
time, duration, LLM provider/model, step counts).  Report data is excluded
to keep the response lightweight; use GET /api/v1/results/{run_id} for that.
"""

from __future__ import annotations

import asyncpg
import structlog
from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_db_pool
from app.api.models.responses import RunsListResponse, RunSummary
from app.infrastructure.repositories.report_repository import ReportRepository

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

router = APIRouter()

_MAX_LIMIT = 200


@router.get(
    "/runs",
    response_model=RunsListResponse,
    summary="List completed analysis runs",
    description=(
        "Returns a paginated list of all successfully completed pipeline runs, "
        "ordered by completion time descending.  Report data is not included; "
        "use GET /api/v1/results/{run_id} to fetch the full report."
    ),
)
async def list_runs(
    limit: int = Query(default=50, ge=1, le=_MAX_LIMIT, description="Page size (1-200)"),
    offset: int = Query(default=0, ge=0, description="Number of items to skip"),
    db_pool: asyncpg.Pool = Depends(get_db_pool),  # noqa: B008
) -> RunsListResponse:
    """Return all successfully completed analysis runs with metadata."""
    repo = ReportRepository(db_pool)
    rows = await repo.get_completed_runs(limit=limit, offset=offset)

    logger.info("Completed runs listed", count=len(rows), limit=limit, offset=offset)

    runs = [
        RunSummary(
            run_id=row["run_id"],
            ticker=str(row["ticker"]),
            status=str(row["status"]),
            created_at=row["created_at"].isoformat(),
            completed_at=row["completed_at"].isoformat(),
            duration_ms=row.get("duration_ms"),
            llm_provider=str(row["llm_provider"]),
            llm_model=str(row["llm_model"]) if row.get("llm_model") else None,
            steps_total=int(row["steps_total"]),
            steps_completed=int(row["steps_completed"]),
            steps_failed=int(row["steps_failed"]),
        )
        for row in rows
    ]

    return RunsListResponse(
        total=len(runs),
        limit=limit,
        offset=offset,
        runs=runs,
    )
