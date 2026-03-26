from __future__ import annotations

import asyncio
from typing import Any

import asyncpg
import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.dependencies import get_db_pool, get_redis, get_settings
from app.config import Settings

router = APIRouter()


@router.get("/health")
async def health_check(
    db_pool: asyncpg.Pool = Depends(get_db_pool),  # noqa: B008
    redis: Any = Depends(get_redis),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> JSONResponse:
    """
    Returns 200 if all critical dependencies (DB + Redis) are reachable.
    Returns 503 if either is down.
    Ollama is checked as informational only — its status never causes 503.
    """
    checks: dict[str, str] = {}

    # ── Database ──────────────────────────────────────────────
    try:
        async with db_pool.acquire(timeout=2) as conn:
            await conn.fetchval("SELECT 1")
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {str(exc)[:50]}"

    # ── Redis ─────────────────────────────────────────────────
    try:
        await asyncio.wait_for(redis.ping(), timeout=2)
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {str(exc)[:50]}"

    # ── Ollama (informational — never causes 503) ─────────────
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{settings.ollama_url}/api/tags")
            checks["ollama"] = "ok" if r.status_code == 200 else f"status:{r.status_code}"
    except Exception:
        checks["ollama"] = "unreachable"

    is_healthy = checks["database"] == "ok" and checks["redis"] == "ok"

    return JSONResponse(
        status_code=200 if is_healthy else 503,
        content={
            "status": "healthy" if is_healthy else "degraded",
            "checks": checks,
            "version": settings.app_version,
        },
    )
