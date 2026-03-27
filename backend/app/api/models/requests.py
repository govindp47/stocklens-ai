"""API request models for StockLens AI.

Architecture reference: 07_SECURITY_MODEL.md § 2 (SSRF analysis — ticker regex).
"""

from __future__ import annotations

import re

from pydantic import BaseModel, field_validator

# Ticker regex from 07_SECURITY_MODEL.md § 2:
# Allows 1–5 uppercase letters, optionally followed by a dot and 1–3 uppercase letters.
# Examples: AAPL, BRK.B, GOOGL.  Rejects: 123, aapl, TOOLONG, $$$.
_TICKER_RE: re.Pattern[str] = re.compile(r"^[A-Z]{1,5}(\.[A-Z]{1,3})?$")


class AnalyzeRequest(BaseModel):
    """Request body for POST /api/v1/analyze.

    The ``ticker`` field is normalised (stripped + uppercased) before
    validation so clients may submit ``"aapl"`` or ``" AAPL "`` and receive
    the same result as ``"AAPL"``.
    """

    ticker: str

    @field_validator("ticker", mode="before")
    @classmethod
    def uppercase_and_strip(cls, v: object) -> str:
        """Strip whitespace and uppercase the ticker before format validation."""
        if isinstance(v, str):
            return v.strip().upper()
        # Return as-is; the type error will be caught by Pydantic's own coercion.
        return str(v)

    @field_validator("ticker")
    @classmethod
    def validate_ticker_format(cls, v: str) -> str:
        """Enforce the ticker symbol regex: ^[A-Z]{1,5}(\\.[A-Z]{1,3})?$"""
        if not _TICKER_RE.match(v):
            raise ValueError(
                "ticker must be 1–5 uppercase letters, optionally followed by "
                "a dot and 1–3 uppercase letters (e.g. AAPL, BRK.B)"
            )
        return v
