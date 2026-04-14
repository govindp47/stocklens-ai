"""AI-generated insights domain models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.lib.constants import AI_ANALYSIS_DISCLAIMER


class InsightSections(BaseModel):
    """Six structured sections produced by the InsightGenerator pipeline step.

    All fields are LLM-generated prose; none are sourced from user input.
    """

    model_config = ConfigDict(frozen=True)

    company_overview: str = ""
    recent_developments: str = ""
    sentiment_overview: str = ""
    potential_drivers: str = ""
    potential_risks: str = ""
    ai_summary: str = ""


class InsightsResult(BaseModel):
    """Container for the insights section of an analysis report.

    disclaimer is always populated from the AI_ANALYSIS_DISCLAIMER constant —
    it is never sourced from LLM output or user input.
    """

    model_config = ConfigDict(frozen=True)

    available: bool = False
    sections: InsightSections | None = None
    disclaimer: str = AI_ANALYSIS_DISCLAIMER
