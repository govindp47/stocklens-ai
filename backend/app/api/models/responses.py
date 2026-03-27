"""API response models for StockLens AI."""

from __future__ import annotations

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
