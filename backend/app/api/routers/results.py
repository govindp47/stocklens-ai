"""GET /api/v1/results/{run_id} — retrieve a completed analysis report.

Returns the full AnalysisReport JSON for a completed pipeline run.
Returns 404 for unknown runs, soft-deleted runs, and non-complete runs
(with run status in the detail so the client knows whether to retry).
"""

from __future__ import annotations

import json
from uuid import UUID

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.dependencies import get_db_pool
from app.api.models.responses import ResultsResponse
from app.infrastructure.repositories.report_repository import ReportRepository

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

router = APIRouter()


@router.get(
    "/results/{run_id}",
    response_model=ResultsResponse,
    summary="Retrieve a completed analysis report",
    description=(
        "Returns the full AnalysisReport for a completed pipeline run. "
        "Returns 404 if the run is unknown, deleted, or not yet complete."
    ),
)
async def get_results(
    run_id: UUID,
    request: Request,
    db_pool: asyncpg.Pool = Depends(get_db_pool),  # noqa: B008
) -> ResultsResponse:
    """Retrieve the report for a completed analysis run."""
    log = logger.bind(run_id=str(run_id))
    repo = ReportRepository(db_pool)

    row = await repo.get_run_by_id(run_id)

    if row is None:
        log.info("Results requested for unknown run")
        raise HTTPException(status_code=404, detail="Run not found.")

    status = row.get("status")
    if status != "complete":
        log.info("Results requested for non-complete run", status=status)
        raise HTTPException(
            status_code=404,
            detail=f"Run is not complete (current status: {status}).",
        )

    report_data = row.get("report_data")
    if report_data is None:
        log.warning("Complete run has no report_data")
        raise HTTPException(status_code=404, detail="Report data not available.")

    # asyncpg may return report_data as a str (JSON) or already-parsed dict
    if isinstance(report_data, str):
        report_dict = json.loads(report_data)
    else:
        report_dict = dict(report_data)

    log.info("Results retrieved", ticker=row.get("ticker"))
    return ResultsResponse(
        run_id=run_id,
        ticker=str(row["ticker"]),
        status=str(status),
        report=report_dict,
    )
