"""Unit tests for RedisSlidingWindowRateLimiter (T-027).

All tests use fakeredis — no real Redis required.
"""

from __future__ import annotations

import asyncio
import time

import fakeredis
import fakeredis.aioredis as aioredis_fakeredis
import pytest

from app.infrastructure.rate_limiter import (
    RedisSlidingWindowRateLimiter,
    _hash_ip,
    endpoint_slug,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def redis() -> aioredis_fakeredis.FakeRedis:  # type: ignore[type-arg]
    """Fresh isolated fakeredis instance for each test (separate FakeServer)."""
    server = fakeredis.FakeServer()
    return aioredis_fakeredis.FakeRedis(server=server)


def _limiter(
    redis: aioredis_fakeredis.FakeRedis,  # type: ignore[type-arg]
    window_seconds: int = 60,
) -> RedisSlidingWindowRateLimiter:
    return RedisSlidingWindowRateLimiter(redis=redis, window_seconds=window_seconds)


# ── endpoint_slug helper ──────────────────────────────────────────────────────


@pytest.mark.unit
class TestEndpointSlug:
    def test_post_analyze(self) -> None:
        assert endpoint_slug("POST /api/v1/analyze") == "post_analyze"

    def test_get_analyze_with_id(self) -> None:
        assert endpoint_slug("GET /api/v1/analyze/abc123") == "get_analyze"

    def test_get_health(self) -> None:
        assert endpoint_slug("GET /health") == "get_health"

    def test_lowercase_method(self) -> None:
        assert endpoint_slug("post /api/v1/analyze") == "post_analyze"

    def test_root_path(self) -> None:
        slug = endpoint_slug("GET /")
        assert slug.startswith("get_")


# ── IP hashing ────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestIpHashing:
    def test_hash_is_16_chars(self) -> None:
        assert len(_hash_ip("192.168.1.1")) == 16

    def test_hash_is_hex(self) -> None:
        h = _hash_ip("10.0.0.1")
        assert all(c in "0123456789abcdef" for c in h)

    def test_different_ips_different_hashes(self) -> None:
        assert _hash_ip("1.2.3.4") != _hash_ip("5.6.7.8")

    def test_same_ip_same_hash(self) -> None:
        assert _hash_ip("1.2.3.4") == _hash_ip("1.2.3.4")


# ── Core rate limit behaviour ─────────────────────────────────────────────────


@pytest.mark.unit
class TestRateLimitBehaviour:
    async def test_allows_within_limit(self, redis: aioredis_fakeredis.FakeRedis) -> None:  # type: ignore[type-arg]
        """Requests up to the limit are all allowed."""
        limiter = _limiter(redis)
        # Override _ENDPOINT_LIMITS by testing with a slug that has limit=10
        for _ in range(10):
            allowed, _ = await limiter.check("1.2.3.4", "POST /api/v1/analyze")
            assert allowed is True

    async def test_rejects_at_limit_plus_one(self, redis: aioredis_fakeredis.FakeRedis) -> None:  # type: ignore[type-arg]
        """The (limit+1)th request in the window is rejected."""
        limiter = _limiter(redis)
        # POST /analyze has limit=10; send 11 requests
        results = []
        for _ in range(11):
            allowed, count = await limiter.check("1.2.3.4", "POST /api/v1/analyze")
            results.append(allowed)

        assert results[:10] == [True] * 10
        assert results[10] is False

    async def test_independent_limits_per_ip(self, redis: aioredis_fakeredis.FakeRedis) -> None:  # type: ignore[type-arg]
        """Two different IPs have completely independent counters."""
        limiter = _limiter(redis)
        endpoint = "POST /api/v1/analyze"  # limit = 10

        # Exhaust IP A's limit
        for _ in range(10):
            allowed, _ = await limiter.check("192.168.0.1", endpoint)
            assert allowed is True
        allowed_a, _ = await limiter.check("192.168.0.1", endpoint)
        assert allowed_a is False

        # IP B should still be allowed
        allowed_b, count_b = await limiter.check("10.0.0.1", endpoint)
        assert allowed_b is True
        assert count_b == 1

    async def test_count_increments_per_request(self, redis: aioredis_fakeredis.FakeRedis) -> None:  # type: ignore[type-arg]
        limiter = _limiter(redis)
        counts = []
        for _ in range(5):
            _, count = await limiter.check("1.2.3.4", "GET /health")
            counts.append(count)
        assert counts == [1, 2, 3, 4, 5]

    async def test_window_expiry_allows_new_requests(self, redis: aioredis_fakeredis.FakeRedis) -> None:  # type: ignore[type-arg]
        """After the window expires, a new request is permitted from count=1."""
        # Use a 1-second window for a fast test
        limiter = _limiter(redis, window_seconds=1)
        endpoint = "POST /api/v1/analyze"

        # Exhaust the limit
        for _ in range(10):
            await limiter.check("1.2.3.4", endpoint)
        allowed_before, _ = await limiter.check("1.2.3.4", endpoint)
        assert allowed_before is False

        # Wait for the window to expire
        await asyncio.sleep(1.1)

        # After expiry, the sliding window should have zero old members;
        # the new request is the only member → count = 1 → allowed
        allowed_after, count_after = await limiter.check("1.2.3.4", endpoint)
        assert allowed_after is True
        assert count_after == 1

    async def test_independent_limits_per_endpoint(self, redis: aioredis_fakeredis.FakeRedis) -> None:  # type: ignore[type-arg]
        """Different endpoints on the same IP have independent counters."""
        limiter = _limiter(redis)

        # POST /analyze (limit=10) — exhaust it
        for _ in range(10):
            await limiter.check("1.2.3.4", "POST /api/v1/analyze")
        allowed_analyze, _ = await limiter.check("1.2.3.4", "POST /api/v1/analyze")
        assert allowed_analyze is False

        # GET /health (limit=300) on same IP — should still be allowed
        allowed_health, count_health = await limiter.check("1.2.3.4", "GET /health")
        assert allowed_health is True
        assert count_health == 1


# ── Key structure ─────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestKeyStructure:
    async def test_raw_ip_not_in_key(self, redis: aioredis_fakeredis.FakeRedis) -> None:  # type: ignore[type-arg]
        """Redis keys must not contain the raw IP address."""
        limiter = _limiter(redis)
        ip = "203.0.113.42"
        await limiter.check(ip, "GET /health")

        keys = await redis.keys("rl:*")
        for k in keys:
            key_str = k.decode() if isinstance(k, bytes) else k
            assert ip not in key_str, f"Raw IP found in key: {key_str}"

    async def test_key_contains_hashed_ip_prefix(self, redis: aioredis_fakeredis.FakeRedis) -> None:  # type: ignore[type-arg]
        ip = "203.0.113.42"
        expected_hash = _hash_ip(ip)
        limiter = _limiter(redis)
        await limiter.check(ip, "GET /health")

        keys = await redis.keys("rl:*")
        key_str = keys[0].decode() if isinstance(keys[0], bytes) else keys[0]
        assert expected_hash in key_str
