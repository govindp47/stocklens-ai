"""Unit tests for RedisEventBus dual-write implementation.

Uses the in-process fakeredis fixture from conftest.py — no external Redis
connection required.
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from app.infrastructure.event_bus import RedisEventBus

# ──────────────────────────────────────────────────────────────────────────────
# Dual-write behaviour
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit()
async def test_event_published_to_both_pubsub_and_list(redis: object) -> None:  # type: ignore[type-arg]
    """Every publish() call must write to both the Pub/Sub channel and the List."""
    bus = RedisEventBus(redis)  # type: ignore[arg-type]
    run_id = uuid4()
    event = {"type": "step_event", "step_name": "ticker_validator", "run_id": str(run_id)}

    await bus.publish(run_id, event)

    buffered = await bus.get_buffered_events(run_id)
    assert len(buffered) == 1
    parsed = json.loads(buffered[0])
    assert parsed["type"] == "step_event"
    assert parsed["step_name"] == "ticker_validator"


@pytest.mark.unit()
async def test_buffered_events_order_preserved(redis: object) -> None:  # type: ignore[type-arg]
    """Events must be returned from get_buffered_events in insertion order."""
    bus = RedisEventBus(redis)  # type: ignore[arg-type]
    run_id = uuid4()

    events = [{"type": "step_event", "step_index": i} for i in range(5)]
    for e in events:
        await bus.publish(run_id, e)

    buffered = await bus.get_buffered_events(run_id)
    assert len(buffered) == 5
    for i, raw in enumerate(buffered):
        parsed = json.loads(raw)
        assert parsed["step_index"] == i


@pytest.mark.unit()
async def test_multiple_publish_appends_to_list(redis: object) -> None:  # type: ignore[type-arg]
    """Calling publish() N times results in N entries in the List."""
    bus = RedisEventBus(redis)  # type: ignore[arg-type]
    run_id = uuid4()

    for i in range(3):
        await bus.publish(run_id, {"type": "step_event", "n": i})

    buffered = await bus.get_buffered_events(run_id)
    assert len(buffered) == 3


@pytest.mark.unit()
async def test_buffered_events_empty_for_unknown_run(redis: object) -> None:  # type: ignore[type-arg]
    bus = RedisEventBus(redis)  # type: ignore[arg-type]
    buffered = await bus.get_buffered_events(uuid4())
    assert buffered == []


# ──────────────────────────────────────────────────────────────────────────────
# TTL
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit()
async def test_list_ttl_set_after_publish(redis: object) -> None:  # type: ignore[type-arg]
    """The Redis List key must have a TTL set to ≤25 h after the first write."""
    bus = RedisEventBus(redis)  # type: ignore[arg-type]
    run_id = uuid4()

    await bus.publish(run_id, {"type": "step_event"})

    list_key = f"pipeline:list:{run_id}"
    ttl = await redis.ttl(list_key)  # type: ignore[union-attr]
    assert 0 < ttl <= 25 * 3600


# ──────────────────────────────────────────────────────────────────────────────
# Sentinel key (terminal event detection)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit()
async def test_sentinel_key_set_on_pipeline_complete(redis: object) -> None:  # type: ignore[type-arg]
    bus = RedisEventBus(redis)  # type: ignore[arg-type]
    run_id = uuid4()

    await bus.publish(
        run_id,
        {
            "type": "pipeline_complete",
            "run_id": str(run_id),
            "steps_completed": 9,
        },
    )

    assert await bus.is_run_complete(run_id)


@pytest.mark.unit()
async def test_sentinel_key_set_on_pipeline_failed(redis: object) -> None:  # type: ignore[type-arg]
    bus = RedisEventBus(redis)  # type: ignore[arg-type]
    run_id = uuid4()

    await bus.publish(
        run_id,
        {
            "type": "pipeline_failed",
            "run_id": str(run_id),
            "reason": "critical step",
        },
    )

    assert await bus.is_run_complete(run_id)


@pytest.mark.unit()
async def test_sentinel_key_set_on_pipeline_timeout(redis: object) -> None:  # type: ignore[type-arg]
    bus = RedisEventBus(redis)  # type: ignore[arg-type]
    run_id = uuid4()

    await bus.publish(run_id, {"type": "pipeline_timeout", "run_id": str(run_id)})

    assert await bus.is_run_complete(run_id)


@pytest.mark.unit()
async def test_sentinel_not_set_for_step_events(redis: object) -> None:  # type: ignore[type-arg]
    """Non-terminal events must NOT set the sentinel key."""
    bus = RedisEventBus(redis)  # type: ignore[arg-type]
    run_id = uuid4()

    await bus.publish(run_id, {"type": "step_event", "run_id": str(run_id)})
    await bus.publish(run_id, {"type": "pipeline_started", "run_id": str(run_id)})

    assert not await bus.is_run_complete(run_id)


@pytest.mark.unit()
async def test_sentinel_key_ttl_set(redis: object) -> None:  # type: ignore[type-arg]
    """The sentinel key must also carry a TTL."""
    bus = RedisEventBus(redis)  # type: ignore[arg-type]
    run_id = uuid4()

    await bus.publish(
        run_id,
        {
            "type": "pipeline_complete",
            "run_id": str(run_id),
            "steps_completed": 9,
        },
    )

    sentinel_key = f"run:complete:{run_id}"
    ttl = await redis.ttl(sentinel_key)  # type: ignore[union-attr]
    assert 0 < ttl <= 25 * 3600
