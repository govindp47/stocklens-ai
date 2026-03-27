"""Step 4 — NewsDeduplicator (non-critical pipeline step).

Two-pass deduplication of raw RSS articles:

  Pass 1 — Exact URL deduplication.
            Articles sharing the same URL are deduplicated on first-seen basis.

  Pass 2 — SimHash near-duplicate detection.
            Each article title is reduced to a 64-bit SimHash fingerprint using
            MurmurHash3 (mmh3.hash64).  Two articles are considered near-duplicates
            if their fingerprints have Hamming distance ≤ 3.

Both passes use only in-memory computation — no I/O, no retries needed.
"""

from __future__ import annotations

import logging
import re
import time

import mmh3

from app.domain.models.news import RawArticle
from app.pipeline.context import PipelineContext
from app.pipeline.steps.base import BasePipelineStep, StepResult, StepStatus

logger = logging.getLogger(__name__)

# Maximum Hamming distance treated as a near-duplicate (inclusive)
_HAMMING_THRESHOLD: int = 3

# Pre-compiled tokenizer: split on whitespace and non-alphanumeric characters
_TOKEN_RE: re.Pattern[str] = re.compile(r"[\s\W]+")

# 64-bit mask for unsigned arithmetic
_MASK64: int = 0xFFFF_FFFF_FFFF_FFFF


# ── SimHash primitives ────────────────────────────────────────────────────────


def _tokenize(text: str) -> list[str]:
    """Lowercase and split *text* on whitespace/punctuation; drop empty tokens."""
    return [tok for tok in _TOKEN_RE.split(text.lower()) if tok]


def _simhash(text: str) -> int:
    """Return a 64-bit unsigned SimHash fingerprint for *text*.

    Algorithm:
    1. Tokenise text into lowercased words.
    2. For each token, compute a 64-bit MurmurHash3 (unsigned).
    3. Maintain a 64-element integer vector v.  For each bit i:
         if bit i of the token hash is 1 → v[i] += 1
         else                             → v[i] -= 1
    4. Build the fingerprint: bit i = 1 if v[i] > 0 else 0.

    Returns 0 for empty or whitespace-only text.
    """
    tokens = _tokenize(text)
    if not tokens:
        return 0

    # Weighted bit-vector accumulator
    v: list[int] = [0] * 64

    for token in tokens:
        # mmh3.hash64 returns (high64, low64); take the first unsigned value
        h: int = mmh3.hash64(token, signed=False)[0]
        for i in range(64):
            if (h >> i) & 1:
                v[i] += 1
            else:
                v[i] -= 1

    fingerprint = 0
    for i in range(64):
        if v[i] > 0:
            fingerprint |= 1 << i

    return fingerprint


def _hamming_distance(a: int, b: int) -> int:
    """Return the number of differing bits between two 64-bit integers."""
    return bin(a ^ b).count("1")


# ── Deduplication passes ──────────────────────────────────────────────────────


def _exact_url_dedup(articles: list[RawArticle]) -> list[RawArticle]:
    """Pass 1: remove articles with duplicate URLs, keeping the first occurrence."""
    seen: set[str] = set()
    result: list[RawArticle] = []
    for article in articles:
        if article.url not in seen:
            seen.add(article.url)
            result.append(article)
    return result


def _simhash_dedup(articles: list[RawArticle]) -> list[RawArticle]:
    """Pass 2: remove near-duplicate headlines via SimHash Hamming distance ≤ 3.

    O(n²) comparison — acceptable for n ≤ 20 articles per pipeline run.
    The first article in the list is always retained; subsequent articles are
    dropped if their title's SimHash is within the threshold of any retained one.
    """
    if not articles:
        return []

    fingerprints: list[int] = [_simhash(a.title) for a in articles]
    retained_indices: list[int] = []

    for i, fp in enumerate(fingerprints):
        is_duplicate = any(
            _hamming_distance(fp, fingerprints[j]) <= _HAMMING_THRESHOLD
            for j in retained_indices
        )
        if not is_duplicate:
            retained_indices.append(i)

    return [articles[i] for i in retained_indices]


# ── Step ──────────────────────────────────────────────────────────────────────


class NewsDeduplicator(BasePipelineStep):
    """Deduplicate raw articles using exact URL matching and SimHash comparison.

    Attributes:
        name: Step identifier used in logging, metrics, and persistence.
        step_index: Execution order index (4 = fourth step).
        critical: False — deduplication failure is tolerable.
        max_retries: 0 — pure in-memory computation; retrying is pointless.
    """

    name: str = "NewsDeduplicator"
    step_index: int = 4
    critical: bool = False
    max_retries: int = 0

    # ──────────────────────────────────────────────────────────────────────
    # PipelineStep Protocol
    # ──────────────────────────────────────────────────────────────────────

    def can_execute(self, context: PipelineContext) -> bool:
        """Requires Step 3 (NewsRetriever) to have run (raw_articles not None)."""
        return context.outputs.raw_articles is not None

    async def execute(self, context: PipelineContext) -> StepResult:
        """Run two-pass deduplication and populate context.outputs.deduplicated_articles.

        Input: context.outputs.raw_articles (set by NewsRetriever; may be empty list).
        Output: context.outputs.deduplicated_articles — always a list, never None.
        """
        raw = context.outputs.raw_articles or []
        start_ms = int(time.monotonic() * 1000)

        logger.debug(
            "Starting deduplication",
            extra={"input_count": len(raw)},
        )

        # Pass 1 — exact URL deduplication
        after_pass1 = _exact_url_dedup(raw)

        # Pass 2 — SimHash near-duplicate removal
        after_pass2 = _simhash_dedup(after_pass1)

        context.outputs.deduplicated_articles = after_pass2

        duration_ms = int(time.monotonic() * 1000) - start_ms
        removed = len(raw) - len(after_pass2)
        logger.info(
            "Deduplication complete",
            extra={
                "input_count": len(raw),
                "output_count": len(after_pass2),
                "removed": removed,
                "duration_ms": duration_ms,
            },
        )
        return StepResult(
            step_name=self.name,
            step_index=self.step_index,
            status=StepStatus.COMPLETE,
            duration_ms=duration_ms,
            output_summary=(
                f"input={len(raw)} output={len(after_pass2)} removed={removed}"
            ),
        )
