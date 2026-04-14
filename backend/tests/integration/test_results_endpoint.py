"""Integration tests for GET /api/v1/results/{run_id} endpoint (T-042).

Test cases from 09_TESTING_STRATEGY.md:
  - test_get_results_returns_complete_report
  - test_get_results_returns_404_for_unknown_run
  - test_get_results_returns_404_after_ttl (soft-deleted run)
  - test_get_results_returns_404_for_non_complete_run
"""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import asyncpg
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.routers import results

# ── Test app fixture ───────────────────────────────────────────────────────────


@pytest.fixture()
async def results_client(
    db_pool: asyncpg.Pool,  # type: ignore[type-arg]
) -> AsyncClient:  # type: ignore[misc]
    """Minimal FastAPI app with only the results router wired up."""
    test_app = FastAPI(title="StockLens Results Test")
    test_app.state.db_pool = db_pool
    test_app.include_router(results.router, prefix="/api/v1")

    transport = ASGITransport(app=test_app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac  # type: ignore[misc]


# ── Helpers ────────────────────────────────────────────────────────────────────

_SAMPLE_REPORT = {
    "ticker": "AAPL",
    "completeness": "complete",
    "content_hash": "deadbeef1234",
    "sentiment": {
        "available": True,
        "distribution": {"positive": 60, "negative": 20, "neutral": 20},
    },
}


async def _insert_run(
    db_pool: asyncpg.Pool,  # type: ignore[type-arg]
    *,
    run_id: UUID,
    ticker: str = "AAPL",
    status: str = "complete",
    report_data: dict | None = None,
    is_deleted: bool = False,
) -> None:
    report_json = json.dumps(report_data or _SAMPLE_REPORT)
    async with db_pool.acquire() as conn:  # type: ignore[attr-defined]
        await conn.execute(
            """
            INSERT INTO analysis_runs
                (run_id, ticker, status, llm_provider, steps_total, steps_completed,
                 steps_failed, report_data, is_deleted)
            VALUES ($1, $2, $3, 'ollama', 9, 9, 0, $4::jsonb, $5)
            """,
            run_id,
            ticker,
            status,
            report_json,
            is_deleted,
        )


# ── Tests ──────────────────────────────────────────────────────────────────────


@pytest.mark.integration()
class TestGetResultsEndpoint:
    async def test_get_results_returns_complete_report(
        self,
        results_client: AsyncClient,
        db_pool: asyncpg.Pool,  # type: ignore[type-arg]
    ) -> None:
        """200 OK with full report JSON for a completed run."""
        run_id = uuid4()
        await _insert_run(db_pool, run_id=run_id, status="complete")

        response = await results_client.get(f"/api/v1/results/{run_id}")

        assert response.status_code == 200
        body = response.json()
        assert body["run_id"] == str(run_id)
        assert body["ticker"] == "AAPL"
        assert body["status"] == "complete"
        assert isinstance(body["report"], dict)
        assert body["report"]["ticker"] == "AAPL"
        assert "completeness" in body["report"]

    async def test_get_results_returns_404_for_unknown_run(
        self,
        results_client: AsyncClient,
    ) -> None:
        """404 for a run_id that does not exist in the database."""
        unknown_id = uuid4()
        response = await results_client.get(f"/api/v1/results/{unknown_id}")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    async def test_get_results_returns_404_after_ttl(
        self,
        results_client: AsyncClient,
        db_pool: asyncpg.Pool,  # type: ignore[type-arg]
    ) -> None:
        """404 for a soft-deleted run (is_deleted=True)."""
        run_id = uuid4()
        await _insert_run(db_pool, run_id=run_id, status="complete", is_deleted=True)

        response = await results_client.get(f"/api/v1/results/{run_id}")
        assert response.status_code == 404

    async def test_get_results_returns_404_for_non_complete_run(
        self,
        results_client: AsyncClient,
        db_pool: asyncpg.Pool,  # type: ignore[type-arg]
    ) -> None:
        """404 for a run that exists but is not yet complete (e.g. 'in_progress')."""
        run_id = uuid4()
        async with db_pool.acquire() as conn:  # type: ignore[attr-defined]
            await conn.execute(
                """
                INSERT INTO analysis_runs
                    (run_id, ticker, status, llm_provider, steps_total,
                     steps_completed, steps_failed)
                VALUES ($1, 'MSFT', 'in_progress', 'ollama', 9, 3, 0)
                """,
                run_id,
            )

        response = await results_client.get(f"/api/v1/results/{run_id}")
        assert response.status_code == 404
        assert "in_progress" in response.json()["detail"]

    async def test_get_results_returns_404_for_failed_run(
        self,
        results_client: AsyncClient,
        db_pool: asyncpg.Pool,  # type: ignore[type-arg]
    ) -> None:
        """404 for a run in 'failed' status."""
        run_id = uuid4()
        async with db_pool.acquire() as conn:  # type: ignore[attr-defined]
            await conn.execute(
                """
                INSERT INTO analysis_runs
                    (run_id, ticker, status, llm_provider, steps_total,
                     steps_completed, steps_failed)
                VALUES ($1, 'TSLA', 'failed', 'ollama', 9, 2, 1)
                """,
                run_id,
            )

        response = await results_client.get(f"/api/v1/results/{run_id}")
        assert response.status_code == 404

    async def test_get_results_report_is_parseable_json(
        self,
        results_client: AsyncClient,
        db_pool: asyncpg.Pool,  # type: ignore[type-arg]
    ) -> None:
        """The report field in the response is a valid dict (not a string)."""
        run_id = uuid4()
        complex_report = {
            "ticker": "AAPL",
            "completeness": "complete",
            "content_hash": "abc123",
            "sentiment": {
                "available": True,
                "distribution": {"positive": 60, "negative": 20, "neutral": 20},
                "dominant_label": "Mostly Positive",
            },
        }
        await _insert_run(db_pool, run_id=run_id, report_data=complex_report)

        response = await results_client.get(f"/api/v1/results/{run_id}")
        assert response.status_code == 200
        body = response.json()
        # report must be a dict, not a JSON string
        assert isinstance(body["report"], dict)
        assert body["report"]["sentiment"]["distribution"]["positive"] == 60
