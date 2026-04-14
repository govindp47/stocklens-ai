"""EventBus Protocol and RedisEventBus dual-write implementation.

Each call to ``RedisEventBus.publish()`` performs two writes atomically via a
Redis pipeline:
  1. ``PUBLISH pipeline:events:{run_id}``  — live SSE consumers receive the event
     immediately through Pub/Sub.
  2. ``RPUSH pipeline:list:{run_id}``       — all events are appended to a Redis
     List so reconnecting clients can replay missed events via ``get_buffered_events``.

The List key TTL is set to 25 hours on first write (slightly longer than the
24-hour run retention period) so buffers outlive the HTTP session window.

When a terminal event (pipeline_complete / pipeline_failed / pipeline_timeout)
is published, a sentinel key ``run:complete:{run_id}`` is also written (TTL=25h).
The SSE router uses this sentinel to detect already-finished runs on reconnect
and immediately serve the buffered event history rather than waiting on the
Pub/Sub channel.

Architecture reference: 01_SYSTEM_ARCHITECTURE.md (SSE and Redis Pub/Sub pattern).
"""

from __future__ import annotations

import json
from typing import Any, Protocol
from uuid import UUID

from redis.asyncio import Redis

from app.api.models.pipeline_events import TERMINAL_EVENT_TYPES

# Redis key templates — all scoped to run_id to prevent cross-run pollution.
_CHANNEL_KEY = "pipeline:events:{run_id}"
_LIST_KEY = "pipeline:list:{run_id}"
_SENTINEL_KEY = "run:complete:{run_id}"

# 25 hours in seconds — slightly longer than the 24 h run retention period.
_LIST_TTL_SECONDS = 25 * 3600


class EventBus(Protocol):
    """Pub/Sub interface for pipeline step events.

    Implementations must support:
      - Publish an event dict to a run-scoped channel.
      - Guarantee that events can be replayed on reconnect (via Redis List).
    """

    async def publish(self, run_id: UUID, event: dict[str, Any]) -> None:
        """Publish a pipeline event for the given run.

        Args:
            run_id: The analysis run that produced the event.
            event:  Serialisable dict conforming to the SSE event schema.
        """
        ...


class RedisEventBus:
    """Redis-backed EventBus with Pub/Sub + List dual-write.

    Args:
        redis: An ``asyncio``-compatible Redis client (``redis.asyncio.Redis``
               or a ``fakeredis.aioredis.FakeRedis`` for tests).
    """

    def __init__(self, redis: Redis) -> None:  # type: ignore[type-arg]
        self._redis = redis

    async def publish(self, run_id: UUID, event: dict[str, Any]) -> None:
        """Write ``event`` to both the Pub/Sub channel and the Redis List.

        Both writes are issued inside a single Redis pipeline so they are sent
        to the server in one round-trip.  The pipeline is not a MULTI/EXEC
        transaction — if one command fails the other may still succeed — but
        the latency benefit is significant and atomicity is not required for
        correctness here.

        Sets the List TTL to 25 h after every ``rpush`` (the EXPIRE command is
        idempotent for our purposes: it refreshes the TTL, keeping the list
        alive for at least 25 h from the most recent event).
        """
        run_id_str = str(run_id)
        channel = _CHANNEL_KEY.format(run_id=run_id_str)
        list_key = _LIST_KEY.format(run_id=run_id_str)

        payload = json.dumps(event, default=str)

        async with self._redis.pipeline(transaction=False) as pipe:
            pipe.publish(channel, payload)
            pipe.rpush(list_key, payload)
            pipe.expire(list_key, _LIST_TTL_SECONDS)

            # Write sentinel for terminal events so the SSE router can detect
            # already-finished runs on reconnect without scanning the list.
            event_type: str = event.get("type", "")
            if event_type in TERMINAL_EVENT_TYPES:
                sentinel_key = _SENTINEL_KEY.format(run_id=run_id_str)
                pipe.set(sentinel_key, event_type, ex=_LIST_TTL_SECONDS)

            await pipe.execute()

    async def get_buffered_events(self, run_id: UUID) -> list[str]:
        """Return all events published for ``run_id`` in insertion order.

        Used by the SSE router to replay missed events when a client reconnects.
        Events are returned as raw JSON strings — callers are responsible for
        deserialisation.

        Returns an empty list if no events have been published (e.g. the run_id
        is invalid or the list has expired).
        """
        list_key = _LIST_KEY.format(run_id=str(run_id))
        raw: list[bytes | str] = await self._redis.lrange(list_key, 0, -1)
        return [item.decode() if isinstance(item, bytes) else item for item in raw]

    async def is_run_complete(self, run_id: UUID) -> bool:
        """Return True if the run has already ended (sentinel key present).

        The SSE router calls this on reconnect to determine whether to serve
        buffered history and close the connection immediately.
        """
        sentinel_key = _SENTINEL_KEY.format(run_id=str(run_id))
        return bool(await self._redis.exists(sentinel_key))
