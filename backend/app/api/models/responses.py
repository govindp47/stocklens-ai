"""API response models for StockLens AI."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel


class AnalyzeResponse(BaseModel):
    """Response body for POST /api/v1/analyze (202 Accepted).

    Attributes:
        run_id: The UUID of the newly created (or existing idempotent) analysis run.
        status: Always ``"accepted"`` for a 202 response.
    """

    run_id: UUID
    status: str


class ResultsResponse(BaseModel):
    """Response body for GET /api/v1/results/{run_id} (200 OK).

    Attributes:
        run_id: UUID of the analysis run.
        ticker: Ticker symbol analysed.
        status: Pipeline status — always ``"complete"`` for a 200 response.
        report: The fully-assembled AnalysisReport as a plain dict (JSON-safe).
    """

    run_id: UUID
    ticker: str
    status: str
    report: dict[str, Any]


class NewsResponse(BaseModel):
    """Response body for GET /api/v1/news/{ticker} (200 OK).

    Attributes:
        ticker: Normalised ticker symbol.
        article_count: Total number of articles returned.
        articles: List of serialised RawArticle dicts.
    """

    ticker: str
    article_count: int
    articles: list[dict[str, Any]]


class RunSummary(BaseModel):
    """Summary metadata for a single completed analysis run.

    Attributes:
        run_id: UUID of the analysis run.
        ticker: Ticker symbol analysed.
        status: Always ``"complete"`` in this list.
        created_at: When the run was submitted (ISO 8601, UTC).
        completed_at: When the run finished (ISO 8601, UTC).
        duration_ms: Wall-clock duration of the pipeline in milliseconds.
        llm_provider: LLM provider used (``"ollama"`` or ``"openai"``).
        llm_model: Specific model name used.
        steps_total: Total pipeline steps.
        steps_completed: Steps that completed successfully.
        steps_failed: Steps that failed.
    """

    run_id: UUID
    ticker: str
    status: str
    created_at: str
    completed_at: str
    duration_ms: int | None
    llm_provider: str
    llm_model: str | None
    steps_total: int
    steps_completed: int
    steps_failed: int


class RunsListResponse(BaseModel):
    """Response body for GET /api/v1/runs (200 OK).

    Attributes:
        total: Number of items returned in this page.
        limit: Page size requested.
        offset: Page offset requested.
        runs: List of completed run summaries.
    """

    total: int
    limit: int
    offset: int
    runs: list[RunSummary]


class MetricsResponse(BaseModel):
    """Response body for GET /api/v1/metrics (200 OK).

    Attributes:
        window_hours: The time window covered (always 24).
        bucket_count: Number of hourly buckets returned.
        buckets: List of hourly metric rows.
    """

    window_hours: int
    bucket_count: int
    buckets: list[dict[str, Any]]
