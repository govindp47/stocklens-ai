"""News data domain models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RawArticle(BaseModel):
    """A single article as retrieved from an RSS feed before summarization."""

    model_config = ConfigDict(frozen=True)

    article_id: str
    url: str
    title: str
    published_at: datetime
    source_name: str
    content_snippet: str = ""


class ArticleSummary(RawArticle):
    """A RawArticle enriched with LLM-generated summarization fields.

    summarization_failed=True means the LLM call failed; the raw article fields
    (title, url, source_name) are still valid and should be displayed.
    """

    summary: str = ""
    topics: list[str] = []
    sentiment: str = ""  # e.g. "positive", "neutral", "negative"
    sentiment_score: float = 0.0
    summarization_failed: bool = False


class NewsCollection(BaseModel):
    """The full set of processed articles for a pipeline run."""

    model_config = ConfigDict(frozen=True)

    available: bool = False
    articles: list[ArticleSummary] = []
