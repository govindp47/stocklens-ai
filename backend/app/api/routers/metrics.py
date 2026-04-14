"""GET /api/v1/metrics — return aggregated system metrics from system_metrics_hourly.

Returns the last 24 hours of hourly aggregated metrics.
Returns an empty metrics structure if no data exists yet.
"""

from __future__ import annotations

import asyncpg
import structlog
from fastapi import APIRouter, Depends, Request

from app.api.dependencies import get_db_pool
from app.api.models.responses import MetricsResponse
from app.infrastructure.repositories.metrics_repository import MetricsRepository

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

router = APIRouter()


@router.get(
    "/metrics",
    response_model=MetricsResponse,
    summary="Retrieve aggregated system metrics",
    description="Returns the last 24 hours of hourly system metrics. "
    "Returns an empty list if no metrics have been recorded yet.",
)
async def get_metrics(
    request: Request,
    db_pool: asyncpg.Pool = Depends(get_db_pool),  # noqa: B008
) -> MetricsResponse:
    """Return recent hourly system metrics."""
    repo = MetricsRepository(db_pool)

    try:
        rows = await repo.get_recent_metrics(hours=24)
    except Exception as exc:
        logger.warning("Metrics fetch failed", error=str(exc))
        rows = []

    # Serialise datetime fields to ISO strings for JSON transport
    buckets = []
    for row in rows:
        bucket: dict[str, object] = {}
        for k, v in row.items():
            if hasattr(v, "isoformat"):
                bucket[k] = v.isoformat()
            else:
                bucket[k] = v
        buckets.append(bucket)

    logger.info("Metrics retrieved", bucket_count=len(buckets))
    return MetricsResponse(
        window_hours=24,
        bucket_count=len(buckets),
        buckets=buckets,
    )
