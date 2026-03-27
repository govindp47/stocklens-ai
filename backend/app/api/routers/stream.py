"""GET /api/v1/analyze/stream/{run_id} — Server-Sent Events stream.

The handler:
  1. Validates that run_id exists in the database; returns 404 if not found.
  2. Returns a StreamingResponse with media_type="text/event-stream".

The event_generator inside the StreamingResponse:
  a. Replays all buffered events from the Redis List (for reconnecting clients).
  b. Checks the sentinel key; if the run already completed, yields a
     ``stream_end`` event and closes the generator immediately.
  c. Otherwise subscribes to the Redis Pub/Sub channel and streams live events
     until a terminal event type (pipeline_complete / pipeline_failed /
     pipeline_timeout) is received, then yields ``stream_end`` and returns.
  d. Unsubscribes and closes the Pub/Sub object in a finally block —
     guarantees no subscriber leak on client disconnect.

Response headers disable Nginx buffering so events reach the client immediately.

Architecture reference: 05_APPLICATION_STRUCTURE.md § 2.5,
01_SYSTEM_ARCHITECTURE.md (SSE delivery pattern).
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from uuid import UUID

import asyncpg
import structlog
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from redis.asyncio import Redis

from app.api.dependencies import get_db_pool, get_redis
from app.api.models.pipeline_events import TERMINAL_EVENT_TYPES
from app.infrastructure.repositories.report_repository import ReportRepository

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

router = APIRouter()

# Redis key templates — must match event_bus.py constants exactly.
_CHANNEL_KEY_TPL = "pipeline:events:{run_id}"
_LIST_KEY_TPL = "pipeline:list:{run_id}"
_SENTINEL_KEY_TPL = "run:complete:{run_id}"

# SSE payload for the synthetic stream_end event sent to the client when the
# generator terminates so the client knows to close the EventSource connection.
_STREAM_END_PAYLOAD: str = json.dumps({"type": "stream_end"})


@router.get(
    "/analyze/stream/{run_id}",
    response_model=None,
    summary="Stream real-time analysis events via SSE",
    description=(
        "Opens a Server-Sent Events stream for the given run_id. "
        "Reconnecting clients receive all buffered events before live events."
    ),
)
async def get_stream(
    run_id: UUID,
    db_pool: asyncpg.Pool = Depends(get_db_pool),  # noqa: B008
    redis: Redis = Depends(get_redis),  # type: ignore[type-arg]  # noqa: B008
) -> StreamingResponse | JSONResponse:
    """Return an SSE StreamingResponse, or 404 if run_id is unknown."""
    report_repo = ReportRepository(db_pool)
    run = await report_repo.get_run_by_id(run_id)
    if run is None:
        logger.info("SSE stream requested for unknown run_id", run_id=str(run_id))
        return JSONResponse(
            status_code=404,
            content={"error": "Run not found", "run_id": str(run_id)},
        )

    logger.info("SSE stream opened", run_id=str(run_id))
    return StreamingResponse(
        _event_generator(run_id, redis),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


async def _event_generator(
    run_id: UUID,
    redis: Redis,  # type: ignore[type-arg]
) -> AsyncGenerator[str, None]:
    """Async generator that yields SSE-formatted event strings.

    Each yielded string has the format ``data: <json>\\n\\n`` as required by
    the SSE specification.

    Steps:
    1. Replay all events from the Redis List (buffered for reconnect).
    2. Check the sentinel key.  If the run already ended:
       - Yield stream_end and return.
    3. Subscribe to the Redis Pub/Sub channel.
    4. Yield live events until a terminal event type is received.
    5. In the finally block, always unsubscribe and close the Pub/Sub object.
    """
    run_id_str = str(run_id)
    list_key = _LIST_KEY_TPL.format(run_id=run_id_str)
    sentinel_key = _SENTINEL_KEY_TPL.format(run_id=run_id_str)
    channel = _CHANNEL_KEY_TPL.format(run_id=run_id_str)

    # ── Step 1: Replay buffered events ────────────────────────────────────────
    # Redis[str] (decode_responses=True) returns list[str] from lrange.
    buffered: list[str] = await redis.lrange(list_key, 0, -1)
    for payload in buffered:
        yield f"data: {payload}\n\n"

    # ── Step 2: Check sentinel (already-completed run) ────────────────────────
    is_complete = bool(await redis.exists(sentinel_key))
    if is_complete:
        yield f"data: {_STREAM_END_PAYLOAD}\n\n"
        return

    # ── Step 3–5: Live Pub/Sub stream ─────────────────────────────────────────
    pubsub = redis.pubsub()
    try:
        await pubsub.subscribe(channel)
        async for message in pubsub.listen():
            if message["type"] != "message":
                # Skip subscription confirmation messages and other control msgs.
                continue

            raw_data: str = message["data"]
            payload = str(raw_data)
            yield f"data: {payload}\n\n"

            # Stop the stream on terminal pipeline events.
            try:
                event = json.loads(payload)
                event_type: str = event.get("type", "")
                if event_type in TERMINAL_EVENT_TYPES:
                    yield f"data: {_STREAM_END_PAYLOAD}\n\n"
                    return
            except (json.JSONDecodeError, AttributeError):
                # Malformed event payload — log and continue; don't break stream.
                logger.warning(
                    "Malformed SSE event payload",
                    run_id=run_id_str,
                    payload=str(payload)[:200],
                )
    finally:
        # Guaranteed cleanup — called on normal return, exception, or disconnect.
        await pubsub.unsubscribe(channel)
        await pubsub.close()
