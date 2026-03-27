"""GET /api/v1/news/{ticker} — return recent news articles for a ticker.

Validates ticker format (same regex as AnalyzeRequest) and fetches
articles from RSSNewsFeedProvider. Returns 422 for invalid ticker format.
Company name defaults to ticker when not provided.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException, Request

from app.api.models.requests import _TICKER_RE
from app.api.models.responses import NewsResponse
from app.domain.models.news import RawArticle

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

router = APIRouter()


@router.get(
    "/news/{ticker}",
    response_model=NewsResponse,
    summary="Retrieve recent news articles for a ticker",
    description=(
        "Fetches and returns recent news articles for the given ticker symbol. "
        "Returns 422 for invalid ticker format."
    ),
)
async def get_news(
    ticker: str,
    request: Request,
) -> NewsResponse:
    """Return news articles for ticker from the RSS news feed provider."""
    # Normalise and validate ticker format
    ticker = ticker.strip().upper()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(
            status_code=422,
            detail=(
                "Invalid ticker format. Must be 1–5 uppercase letters, "
                "optionally followed by a dot and 1–3 uppercase letters (e.g. AAPL, BRK.B)."
            ),
        )

    news_provider = request.app.state.news_feed_provider
    log = logger.bind(ticker=ticker)

    try:
        articles: list[RawArticle] = await news_provider.get_articles(
            ticker=ticker,
            company_name=ticker,  # use ticker as fallback company name
        )
    except Exception as exc:
        log.warning("News feed fetch failed", error=str(exc))
        articles = []

    log.info("News retrieved", count=len(articles))
    return NewsResponse(
        ticker=ticker,
        article_count=len(articles),
        articles=[a.model_dump(mode="json") for a in articles],
    )
