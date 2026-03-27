"""LLM output parser with three-strategy JSON extraction fallback.

Provides:
  - extract_json(): Parse JSON from raw LLM output with three fallback strategies.
  - CORRECTIVE_HINT: Prompt suffix to append on retry after a parse failure.
  - estimate_tokens(): Rough token count estimate (4 chars per token).
  - MAX_PROMPT_TOKENS: Conservative token budget for 4K context models.
  - truncate_articles_to_token_budget(): Progressively remove articles to fit budget.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.domain.exceptions import LLMParseError

# Corrective hint appended to prompt on retry after a parse failure.
# Must begin with "\n\nIMPORTANT:" per architecture specification.
CORRECTIVE_HINT: str = (
    "\n\nIMPORTANT: Your previous response was not valid JSON. "
    "Respond with ONLY the JSON object. "
    "Start your response with { and end with }. "
    "Do not include any other text, explanation, or markdown formatting."
)

# Conservative token budget for 4K context local models.
MAX_PROMPT_TOKENS: int = 3000


def extract_json(raw_output: str) -> dict[str, Any]:
    """Extract JSON from LLM output with three-strategy fallback.

    Strategy 1 — Direct parse: handles clean model output.
    Strategy 2 — Markdown fence stripping: handles output wrapped in
        `` ```json ... ``` `` fences.
    Strategy 3 — Regex extraction: handles output with surrounding
        explanatory text by locating the first ``{...}`` block.

    Args:
        raw_output: The verbatim string returned by the LLM provider.

    Returns:
        Parsed JSON as a dict.

    Raises:
        LLMParseError: If all three strategies fail to produce valid JSON.
    """
    # Strategy 1: Direct parse (clean output)
    try:
        return json.loads(raw_output.strip())  # type: ignore[no-any-return]
    except json.JSONDecodeError:
        pass

    # Strategy 2: Strip markdown code fences
    cleaned = re.sub(r"^```(?:json)?\n?", "", raw_output.strip())
    cleaned = re.sub(r"\n?```$", "", cleaned)
    try:
        return json.loads(cleaned.strip())  # type: ignore[no-any-return]
    except json.JSONDecodeError:
        pass

    # Strategy 3: Find first { ... } block
    match = re.search(r"\{.*\}", raw_output, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            pass

    # All strategies failed
    raise LLMParseError(
        "Failed to extract valid JSON from LLM output",
        step_name="unknown",
        raw_output=raw_output,
    )


def estimate_tokens(text: str) -> int:
    """Rough token count estimate using the 4-chars-per-token heuristic.

    This is used to gate prompt construction only — not for billing.
    For English text, 1 token ≈ 4 characters is a reliable lower bound.

    Args:
        text: The string to estimate tokens for.

    Returns:
        Estimated token count.
    """
    return len(text) // 4


def truncate_articles_to_token_budget(
    articles: list[Any],
    prompt_template: str,
    max_tokens: int = MAX_PROMPT_TOKENS,
) -> list[Any]:
    """Progressively remove articles from the end until the prompt fits the budget.

    The caller is responsible for rendering the final prompt using the returned
    article list.  This function estimates token count against ``prompt_template``
    with the article list rendered inline (as a plain string representation).

    Args:
        articles: List of article objects to include in the prompt.
        prompt_template: The already-rendered prompt string (with articles
            interpolated) used only for token estimation.  Pass the rendered
            prompt so this function can measure its length.
        max_tokens: Maximum allowed estimated token count.

    Returns:
        A (possibly shorter) list of articles that fits within the budget.

    Note:
        If the prompt is already within budget, the original list is returned
        unchanged.  If even an empty list exceeds the budget (unlikely), an
        empty list is returned.
    """
    if estimate_tokens(prompt_template) <= max_tokens:
        return articles

    # Progressively drop articles from the end
    trimmed = list(articles)
    while trimmed and estimate_tokens(prompt_template) > max_tokens:
        trimmed.pop()
        # Recompute a rough proxy: subtract chars per removed article
        # The caller should re-render the prompt with the smaller list;
        # here we shrink proportionally as a conservative guard.
        avg_article_chars = (len(prompt_template) // max(len(articles), 1))
        prompt_template = prompt_template[: len(prompt_template) - avg_article_chars]

    return trimmed
