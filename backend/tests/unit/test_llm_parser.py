"""Unit tests for llm_parser — extract_json with three-strategy fallback."""

from __future__ import annotations

import pytest

from app.domain.exceptions import LLMParseError
from app.infrastructure.providers.llm_parser import (
    CORRECTIVE_HINT,
    MAX_PROMPT_TOKENS,
    estimate_tokens,
    extract_json,
    truncate_articles_to_token_budget,
)

# ── extract_json ───────────────────────────────────────────────────────────────


def test_clean_json() -> None:
    """Strategy 1: direct parse of clean JSON output."""
    raw = '{"summary": "Apple reports record revenue.", "topics": ["Earnings"]}'
    result = extract_json(raw)
    assert result == {"summary": "Apple reports record revenue.", "topics": ["Earnings"]}


def test_strips_markdown_fences() -> None:
    """Strategy 2: strips ```json ... ``` fences before parsing."""
    raw = '```json\n{"sentiment": "positive", "score": 0.9}\n```'
    result = extract_json(raw)
    assert result == {"sentiment": "positive", "score": 0.9}


def test_strips_plain_markdown_fences() -> None:
    """Strategy 2: handles plain ``` without json language tag."""
    raw = '```\n{"key": "value"}\n```'
    result = extract_json(raw)
    assert result == {"key": "value"}


def test_extracts_from_surrounding_text() -> None:
    """Strategy 3: extracts JSON block from surrounding explanatory text."""
    raw = (
        "Here is the JSON you requested:\n"
        '{"sentiment": "neutral", "score": 0.5}\n'
        "I hope this helps!"
    )
    result = extract_json(raw)
    assert result == {"sentiment": "neutral", "score": 0.5}


def test_raises_on_truncated_json() -> None:
    """All strategies fail on truncated JSON — raises LLMParseError."""
    raw = '{"summary": "Apple reports'  # no closing brace
    with pytest.raises(LLMParseError) as exc_info:
        extract_json(raw)
    assert exc_info.value.raw_output == raw


def test_raises_on_no_json() -> None:
    """All strategies fail when there is no JSON at all — raises LLMParseError."""
    raw = "I cannot provide financial advice."
    with pytest.raises(LLMParseError) as exc_info:
        extract_json(raw)
    assert exc_info.value.raw_output == raw


def test_llm_parse_error_preserves_raw_output() -> None:
    """LLMParseError.raw_output must equal the exact input string."""
    raw = "not json at all!!!"
    with pytest.raises(LLMParseError) as exc_info:
        extract_json(raw)
    assert exc_info.value.raw_output == raw
    assert exc_info.value.step_name == "unknown"


# ── CORRECTIVE_HINT ────────────────────────────────────────────────────────────


def test_corrective_hint_starts_with_important() -> None:
    """CORRECTIVE_HINT must begin with '\\n\\nIMPORTANT:' per spec."""
    assert CORRECTIVE_HINT.startswith("\n\nIMPORTANT:")


def test_corrective_hint_is_nonempty() -> None:
    assert len(CORRECTIVE_HINT) > 0


# ── estimate_tokens ────────────────────────────────────────────────────────────


def test_estimate_tokens_four_chars_per_token() -> None:
    """estimate_tokens uses integer division by 4."""
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcdefgh") == 2
    assert estimate_tokens("abc") == 0  # 3 // 4 == 0
    assert estimate_tokens("a" * 4000) == 1000


def test_estimate_tokens_empty_string() -> None:
    assert estimate_tokens("") == 0


# ── MAX_PROMPT_TOKENS ──────────────────────────────────────────────────────────


def test_max_prompt_tokens_value() -> None:
    assert MAX_PROMPT_TOKENS == 3000


# ── truncate_articles_to_token_budget ─────────────────────────────────────────


def test_truncate_articles_no_truncation_needed() -> None:
    """Returns original list when prompt is within budget."""
    articles = [{"title": "A"}, {"title": "B"}]
    short_prompt = "short prompt"
    result = truncate_articles_to_token_budget(articles, short_prompt)
    assert result == articles


def test_truncate_articles_removes_from_end() -> None:
    """Removes articles from the end of the list when over budget."""
    articles = [{"title": f"Article {i}"} for i in range(10)]
    # Build a prompt that exceeds MAX_PROMPT_TOKENS (3000 tokens = 12000 chars)
    long_prompt = "x" * 13000
    result = truncate_articles_to_token_budget(articles, long_prompt)
    # Should return fewer articles than the original
    assert len(result) < len(articles)
    # Remaining articles should be the beginning of the list
    assert result == articles[: len(result)]
