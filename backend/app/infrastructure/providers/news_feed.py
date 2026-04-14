"""RSSNewsFeedProvider — feed parsing, filtering, and normalisation.

All feedparser.parse() calls run in a thread executor (never awaited directly).
Two RSS feed URL templates are fetched concurrently via asyncio.gather.
Relevance filtering, recency filtering, HTML stripping, and sha256-based
article IDs are all applied before returning results.
"""

from __future__ import annotations

import asyncio
import email.utils
import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from typing import Any

import feedparser
import redis.asyncio as aioredis

from app.config import Settings
from app.domain.models.news import RawArticle
from app.infrastructure.cache import cache_get, cache_set

logger = logging.getLogger(__name__)

# Cache TTL: 30 minutes for news feeds (fresh-enough, avoids hammering RSS endpoints)
_FEED_CACHE_TTL: int = 1_800


# ── RSS feed templates ────────────────────────────────────────────────────────

_GOOGLE_NEWS_URL = (
    "https://news.google.com/rss/search" "?q={ticker}+stock&hl=en-US&gl=US&ceid=US:en"
)
_YAHOO_FINANCE_NEWS_URL = (
    "https://feeds.finance.yahoo.com/rss/2.0/headline" "?s={ticker}&region=US&lang=en-US"
)


# ── HTML stripping ────────────────────────────────────────────────────────────


class _HTMLStripper(HTMLParser):
    """Minimal HTMLParser subclass that accumulates non-tag text."""

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def get_text(self) -> str:
        return " ".join(self._parts).strip()


def _strip_html(text: str) -> str:
    """Strip HTML tags from *text* without BeautifulSoup."""
    if not text:
        return ""
    stripper = _HTMLStripper()
    stripper.feed(text)
    return stripper.get_text()


# ── Article ID ────────────────────────────────────────────────────────────────


def _article_id(url: str) -> str:
    """Return sha256(url)[:16] as a deterministic hex article ID."""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


# ── Provider ──────────────────────────────────────────────────────────────────


class RSSNewsFeedProvider:
    """Async RSS news provider with executor-based feedparser calls and Redis caching."""

    def __init__(
        self,
        redis: aioredis.Redis,  # type: ignore[type-arg]
        settings: Settings,
    ) -> None:
        self._redis = redis
        self._settings = settings

    # ──────────────────────────────────────────────────────────────────────
    # Public interface
    # ──────────────────────────────────────────────────────────────────────

    async def get_articles(
        self,
        ticker: str,
        company_name: str,
    ) -> list[RawArticle]:
        """Return relevance-filtered, recency-filtered articles.

        Fetches both RSS feed URLs concurrently via asyncio.gather.
        Results are cached in Redis for 30 minutes per ticker per calendar date.
        """
        date_str = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        cache_key = f"news:feed:{ticker}:{date_str}"

        cached = await cache_get(self._redis, cache_key)
        if cached is not None:
            try:
                raw_list: list[dict[str, Any]] = json.loads(cached)
                return [RawArticle(**item) for item in raw_list]
            except Exception:
                logger.warning(
                    "Corrupt news cache entry; re-fetching",
                    extra={"ticker": ticker},
                )

        # Fetch both feeds concurrently
        google_url = _GOOGLE_NEWS_URL.format(ticker=ticker)
        yahoo_url = _YAHOO_FINANCE_NEWS_URL.format(ticker=ticker)
        google_entries, yahoo_entries = await asyncio.gather(
            self._parse_feed(google_url),
            self._parse_feed(yahoo_url),
        )

        # Merge by valid URLs
        merged: list[dict[str, Any]] = []
        for entry in google_entries + yahoo_entries:
            url = entry.get("url", "")
            if url:
                merged.append(entry)

        # Filter, sort, cap
        cutoff = datetime.now(tz=UTC) - timedelta(days=self._settings.news_window_days)
        articles: list[RawArticle] = []
        for entry in merged:
            article = self._build_article(entry, ticker, company_name, cutoff)
            if article is not None:
                articles.append(article)

        articles.sort(key=lambda a: a.published_at, reverse=True)
        max_articles = self._settings.max_articles_per_run
        articles = articles[:max_articles]

        # Cache the result
        try:
            payload = json.dumps([a.model_dump(mode="json") for a in articles])
            await cache_set(self._redis, cache_key, payload, _FEED_CACHE_TTL)
        except Exception as exc:
            logger.debug("Failed to cache news feed for %s: %s", ticker, exc)
        return articles

    # ──────────────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────────────

    async def _parse_feed(self, url: str) -> list[dict[str, Any]]:
        """Run feedparser.parse(url) in a thread executor.

        Returns a list of normalised entry dicts.  Network errors return [].
        """
        loop = asyncio.get_running_loop()
        try:
            feed = await loop.run_in_executor(None, lambda: feedparser.parse(url))
        except Exception as exc:
            logger.warning("Feed fetch error for %s: %s", url, exc)
            return []

        entries: list[dict[str, Any]] = []
        for entry in getattr(feed, "entries", []):
            link: str = getattr(entry, "link", "") or ""
            title: str = getattr(entry, "title", "") or ""
            summary: str = _strip_html(getattr(entry, "summary", "") or "")
            source: str = getattr(getattr(feed, "feed", None), "title", "") or ""
            published_at = self._parse_date(entry)
            if published_at is None:
                continue  # exclude articles with unparseable dates
            entries.append(
                {
                    "url": link,
                    "title": title,
                    "summary": summary,
                    "source": source,
                    "published_at": published_at,
                }
            )
        return entries

    def _parse_date(self, entry: Any) -> datetime | None:
        """Parse the publication date from a feedparser entry.

        Returns None if the date cannot be parsed — such articles are excluded.
        """
        published_str: str = getattr(entry, "published", "") or ""
        if not published_str:
            return None
        try:
            dt = email.utils.parsedate_to_datetime(published_str)
            # Normalise to UTC-aware datetime
            return dt.astimezone(UTC)
        except Exception:
            return None

    def _build_article(
        self,
        entry: dict[str, Any],
        ticker: str,
        company_name: str,
        cutoff: datetime,
    ) -> RawArticle | None:
        """Apply relevance and recency filters; return None to exclude."""
        published_at: datetime = entry["published_at"]

        # Recency filter
        if published_at < cutoff:
            return None

        title: str = entry.get("title", "")
        description: str = entry.get("summary", "")

        # Relevance filter: case-insensitive substring match on title OR description
        ticker_lower = ticker.lower()
        company_lower = company_name.lower()
        haystack = (title + " " + description).lower()
        if ticker_lower not in haystack and company_lower not in haystack:
            return None

        url: str = entry.get("url", "")
        return RawArticle(
            article_id=_article_id(url),
            url=url,
            title=title,
            published_at=published_at,
            source_name=entry.get("source", ""),
            content_snippet=description[:500],
        )
