"""Integration tests for GET /api/v1/analyze/stream/{run_id} SSE endpoint (T-029, T-030).

Tests:
  - test_sse_returns_404_for_unknown_run
  - test_sse_replay_delivers_buffered_events
  - test_sse_response_has_correct_headers

The stream tests use httpx streaming support to read SSE events line by line.
"""

from __future__ import annotations

import json
from uuid import uuid4

import asyncpg
import fakeredis.aioredis as fakeredis
import pytest
from httpx import AsyncClient

from app.infrastructure.event_bus import RedisEventBus


@pytest.mark.integration()
class TestStreamEndpoint:
    async def test_sse_returns_404_for_unknown_run(self, client: AsyncClient) -> None:
        """GET /analyze/stream with an unknown run_id returns 404."""
        unknown_id = uuid4()
        response = await client.get(f"/api/v1/analyze/stream/{unknown_id}")

        assert response.status_code == 404
        body = response.json()
        assert "error" in body
        # Confirm the run_id is echoed back for debuggability.
        assert str(unknown_id) in body.get("run_id", "")

    async def test_sse_replay_delivers_buffered_events(
        self,
        client: AsyncClient,
        db_pool: asyncpg.Pool,  # type: ignore[type-arg]
        redis_api: fakeredis.FakeRedis,  # type: ignore[type-arg]
    ) -> None:
        """Reconnecting client receives all buffered events then stream_end.

        Steps:
        1. Insert an analysis_runs row directly.
        2. Publish events via RedisEventBus (dual-write to list + pub/sub).
        3. Mark the run complete via the sentinel key.
        4. Connect to the SSE endpoint — all buffered events + stream_end must arrive.
        """
        run_id = uuid4()

        # Create a run row so the 404 guard passes.
        async with db_pool.acquire() as conn:  # type: ignore[attr-defined]
            await conn.execute(
                """
                INSERT INTO analysis_runs
                    (run_id, ticker, ip_address, llm_provider, llm_model,
                     status, steps_total, steps_completed, steps_failed)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                run_id,
                "AAPL",
                "127.0.0.1",
                "ollama",
                None,
                "complete",
                9,
                4,
                0,
            )

        # Publish two events and a terminal pipeline_complete event.
        event_bus = RedisEventBus(redis=redis_api)  # type: ignore[arg-type]
        await event_bus.publish(
            run_id,
            {"type": "pipeline_started", "run_id": str(run_id), "ticker": "AAPL"},
        )
        await event_bus.publish(
            run_id,
            {
                "type": "step_update",
                "run_id": str(run_id),
                "step_name": "TickerValidator",
                "step_index": 1,
                "status": "complete",
            },
        )
        await event_bus.publish(
            run_id,
            {
                "type": "pipeline_complete",
                "run_id": str(run_id),
                "steps_completed": 1,
            },
        )

        # Connect and read the full SSE stream (sentinel is set, so generator
        # replays buffered events and closes immediately).
        response = await client.get(f"/api/v1/analyze/stream/{run_id}")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers.get("X-Accel-Buffering") == "no"

        # Parse SSE lines: each event is "data: <json>\n\n"
        events = _parse_sse_events(response.text)
        event_types = [e.get("type") for e in events]

        assert "pipeline_started" in event_types
        assert "step_update" in event_types
        assert "pipeline_complete" in event_types
        # stream_end is appended by the SSE router after the buffered events.
        assert event_types[-1] == "stream_end"

    async def test_sse_response_headers_disable_buffering(
        self,
        client: AsyncClient,
        db_pool: asyncpg.Pool,  # type: ignore[type-arg]
        redis_api: fakeredis.FakeRedis,  # type: ignore[type-arg]
    ) -> None:
        """Response headers must include Cache-Control and X-Accel-Buffering."""
        run_id = uuid4()

        # Create a run row and mark it complete immediately via sentinel.
        async with db_pool.acquire() as conn:  # type: ignore[attr-defined]
            await conn.execute(
                """
                INSERT INTO analysis_runs
                    (run_id, ticker, ip_address, llm_provider, llm_model,
                     status, steps_total, steps_completed, steps_failed)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                run_id,
                "TSLA",
                "127.0.0.1",
                "ollama",
                None,
                "complete",
                9,
                0,
                0,
            )

        # Publish a terminal event so the sentinel key is written.
        event_bus = RedisEventBus(redis=redis_api)  # type: ignore[arg-type]
        await event_bus.publish(
            run_id,
            {"type": "pipeline_complete", "run_id": str(run_id), "steps_completed": 0},
        )

        response = await client.get(f"/api/v1/analyze/stream/{run_id}")

        assert response.status_code == 200
        assert response.headers.get("Cache-Control") == "no-cache"
        assert response.headers.get("X-Accel-Buffering") == "no"


# ── SSE parsing helper ────────────────────────────────────────────────────────


def _parse_sse_events(text: str) -> list[dict[str, object]]:
    """Parse SSE ``data: <json>`` lines into a list of event dicts."""
    events: list[dict[str, object]] = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data: "):
            payload = line[len("data: ") :]
            try:
                events.append(json.loads(payload))
            except json.JSONDecodeError:
                pass
    return events
