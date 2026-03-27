"""EventBus Protocol and stub Redis implementation.

The full RedisEventBus dual-write implementation (Redis List + Pub/Sub fan-out,
replay from history, subscriber teardown) is implemented in T-019.

At this stage the Protocol is defined so that all type-checked code that
references EventBus as a dependency injection target can be checked by mypy.
"""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID


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
    """Redis-backed EventBus — full implementation in T-019.

    This stub satisfies the EventBus Protocol so it can be wired into
    the dependency injection container before T-019 is complete.
    """

    # TODO: T-019 — implement dual-write (Redis List + Pub/Sub fan-out)

    async def publish(self, run_id: UUID, event: dict[str, Any]) -> None:
        """Stub: no-op until T-019 is implemented."""
        return
