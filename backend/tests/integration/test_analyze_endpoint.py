"""Integration tests for POST /api/v1/analyze endpoint (T-028, T-030).

Tests in this module require a running PostgreSQL test instance.
All Redis operations use in-process fakeredis from the shared conftest.

Test cases from 09_TESTING_STRATEGY.md § 4.2:
  - test_post_analyze_returns_202_with_run_id
  - test_post_analyze_invalid_ticker_returns_422
  - test_post_analyze_rate_limit_returns_429
  - test_post_analyze_idempotency_same_run_id
"""

from __future__ import annotations

from uuid import UUID

import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestAnalyzeEndpoint:

    async def test_post_analyze_returns_202_with_run_id(
        self, client: AsyncClient
    ) -> None:
        """Valid ticker returns 202 with a UUID run_id."""
        response = await client.post("/api/v1/analyze", json={"ticker": "AAPL"})

        assert response.status_code == 202
        body = response.json()
        assert "run_id" in body
        assert "status" in body
        # Validate it's a parseable UUID
        UUID(body["run_id"])
        assert body["status"] == "accepted"

    async def test_post_analyze_lowercase_ticker_normalised(
        self, client: AsyncClient
    ) -> None:
        """Lowercase ticker is normalised to uppercase; returns 202."""
        response = await client.post("/api/v1/analyze", json={"ticker": "msft"})
        assert response.status_code == 202

    async def test_post_analyze_invalid_ticker_digits_returns_422(
        self, client: AsyncClient
    ) -> None:
        """Ticker consisting only of digits returns 422 with field-level error."""
        response = await client.post("/api/v1/analyze", json={"ticker": "123"})

        assert response.status_code == 422
        detail = response.json()["detail"]
        # Pydantic v2 returns a list of error objects; at least one must reference ticker.
        locs = [str(err.get("loc", "")) for err in detail]
        assert any("ticker" in loc for loc in locs)

    async def test_post_analyze_empty_ticker_returns_422(
        self, client: AsyncClient
    ) -> None:
        """Empty ticker returns 422."""
        response = await client.post("/api/v1/analyze", json={"ticker": ""})
        assert response.status_code == 422

    async def test_post_analyze_special_chars_ticker_returns_422(
        self, client: AsyncClient
    ) -> None:
        """Ticker with special characters returns 422."""
        response = await client.post("/api/v1/analyze", json={"ticker": "AA PL"})
        assert response.status_code == 422

    async def test_post_analyze_missing_ticker_returns_422(
        self, client: AsyncClient
    ) -> None:
        """Missing ticker field returns 422."""
        response = await client.post("/api/v1/analyze", json={})
        assert response.status_code == 422

    async def test_post_analyze_rate_limit_returns_429(
        self, client: AsyncClient
    ) -> None:
        """11th request within 60 seconds returns 429 with Retry-After header.

        The rate limit for POST /api/v1/analyze is 10 per 60-second window
        (from rate_limiter._ENDPOINT_LIMITS["post_analyze"]).
        """
        # Exhaust the limit with 10 successful requests (use a unique ticker
        # per test to avoid idempotency short-circuiting the rate limit).
        for _ in range(10):
            r = await client.post("/api/v1/analyze", json={"ticker": "RLTST"})
            assert r.status_code == 202

        # 11th request must be rejected.
        response = await client.post("/api/v1/analyze", json={"ticker": "RLTST"})

        assert response.status_code == 429
        body = response.json()
        assert "retry_after" in body
        assert int(body["retry_after"]) > 0
        assert "Retry-After" in response.headers
        assert int(response.headers["Retry-After"]) > 0

    async def test_post_analyze_idempotency_same_run_id(
        self, client: AsyncClient
    ) -> None:
        """Two rapid submissions of the same ticker from the same IP return the same run_id.

        The idempotency window is 2 minutes. Both requests use the test client's
        address which is constant within a test, so they share an IP+ticker key.
        """
        r1 = await client.post("/api/v1/analyze", json={"ticker": "IDEM"})
        r2 = await client.post("/api/v1/analyze", json={"ticker": "IDEM"})

        assert r1.status_code == 202
        assert r2.status_code == 202
        assert r1.json()["run_id"] == r2.json()["run_id"]

    async def test_post_analyze_different_tickers_different_run_ids(
        self, client: AsyncClient
    ) -> None:
        """Two different tickers from the same IP create separate runs."""
        r1 = await client.post("/api/v1/analyze", json={"ticker": "AAPL"})
        r2 = await client.post("/api/v1/analyze", json={"ticker": "MSFT"})

        assert r1.status_code == 202
        assert r2.status_code == 202
        assert r1.json()["run_id"] != r2.json()["run_id"]

    async def test_post_analyze_openai_key_header_accepted(
        self, client: AsyncClient
    ) -> None:
        """Request with valid X-OpenAI-Key header returns 202."""
        response = await client.post(
            "/api/v1/analyze",
            json={"ticker": "NVDA"},
            headers={"X-OpenAI-Key": "sk-test1234"},
        )
        assert response.status_code == 202
