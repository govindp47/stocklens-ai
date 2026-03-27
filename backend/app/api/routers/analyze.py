"""POST /api/v1/analyze — accepts a ticker and launches an analysis pipeline run.

The handler:
  1. Extracts the client IP (X-Forwarded-For → request.client.host fallback).
  2. Checks the sliding-window rate limit; returns 429 if exceeded.
  3. Checks idempotency: if the same IP submitted the same ticker within
     the last 2 minutes and a run is still active, returns the existing run_id.
  4. Creates a new analysis_runs row in the database.
  5. Launches the pipeline asynchronously via orchestrator.launch().
  6. Returns 202 Accepted with the run_id in < 100 ms.

Architecture reference: 05_APPLICATION_STRUCTURE.md § 2.4,
07_SECURITY_MODEL.md § 4 (idempotency, rate limiting).
"""

from __future__ import annotations

from uuid import uuid4

import asyncpg
import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis

from app.api.dependencies import (
    OllamaProvider,
    OpenAIProvider,
    get_db_pool,
    get_llm_provider,
    get_orchestrator,
    get_redis,
)
from app.api.models.requests import AnalyzeRequest
from app.api.models.responses import AnalyzeResponse
from app.config import get_settings
from app.infrastructure.rate_limiter import RedisSlidingWindowRateLimiter
from app.infrastructure.repositories.report_repository import ReportRepository
from app.pipeline.orchestrator import PipelineOrchestrator

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

router = APIRouter()


def _get_client_ip(request: Request) -> str:
    """Extract the real client IP address.

    Checks ``X-Forwarded-For`` first (populated by Nginx in production).
    Falls back to ``request.client.host`` for direct connections.
    Returns ``"unknown"`` only when both are unavailable (e.g. test env).
    """
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        # X-Forwarded-For may contain a comma-separated chain of IPs;
        # the leftmost is the original client.
        return xff.split(",")[0].strip()
    if request.client is not None:
        return request.client.host
    return "unknown"


@router.post(
    "/analyze",
    status_code=202,
    response_model=AnalyzeResponse,
    summary="Submit a ticker for AI-powered analysis",
    description=(
        "Accepts a ticker symbol and asynchronously starts an analysis pipeline. "
        "Returns 202 with a run_id immediately. Connect to the SSE stream endpoint "
        "to receive real-time progress events."
    ),
)
async def post_analyze(
    request: Request,
    body: AnalyzeRequest,
    db_pool: asyncpg.Pool = Depends(get_db_pool),  # noqa: B008
    redis: Redis = Depends(get_redis),  # type: ignore[type-arg]  # noqa: B008
    orchestrator: PipelineOrchestrator = Depends(get_orchestrator),  # noqa: B008
    llm_provider: OllamaProvider | OpenAIProvider = Depends(  # noqa: B008
        get_llm_provider
    ),
) -> AnalyzeResponse | JSONResponse:
    """Accept a ticker analysis request and return 202 Accepted."""
    settings = get_settings()
    ip = _get_client_ip(request)
    log = logger.bind(ticker=body.ticker, ip=ip)

    # ── 1. Rate limit check ───────────────────────────────────────────────────
    rate_limiter = RedisSlidingWindowRateLimiter(redis)
    allowed, _count = await rate_limiter.check(ip, "POST /api/v1/analyze")
    if not allowed:
        window = settings.rate_limit_window_seconds
        log.warning("Rate limit exceeded", count=_count, window=window)
        return JSONResponse(
            status_code=429,
            content={
                "error": "Rate limit exceeded. Too many requests.",
                "retry_after": window,
            },
            headers={"Retry-After": str(window)},
        )

    # ── 2. Idempotency check ──────────────────────────────────────────────────
    report_repo = ReportRepository(db_pool)
    existing_run_id = await report_repo.get_recent_run_for_ip_and_ticker(
        ip, body.ticker
    )
    if existing_run_id is not None:
        log.info(
            "Idempotent request — returning existing run",
            run_id=str(existing_run_id),
        )
        return AnalyzeResponse(run_id=existing_run_id, status="accepted")

    # ── 3. Create analysis run ────────────────────────────────────────────────
    run_id = uuid4()
    await report_repo.create_run(
        run_id=run_id,
        ticker=body.ticker,
        ip_address=ip,
        llm_provider=llm_provider.model_name,
        llm_model=None,
    )

    # ── 4. Launch pipeline (fire-and-forget asyncio.Task) ─────────────────────
    orchestrator.launch(
        run_id=run_id,
        ticker=body.ticker,
        llm_provider=llm_provider,
    )

    log.info("Analysis run accepted", run_id=str(run_id))
    return AnalyzeResponse(run_id=run_id, status="accepted")
