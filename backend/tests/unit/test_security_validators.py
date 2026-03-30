"""Unit tests for input validation security controls (T-052).

Covers:
* Ticker symbol validation via AnalyzeRequest Pydantic model — XSS, path
  traversal, SQL injection payloads must all be rejected with ValidationError
  (which FastAPI surfaces as HTTP 422).
* X-OpenAI-Key header format guard in get_llm_provider() — keys missing the
  ``sk-`` prefix or exceeding 200 characters silently fall back to OllamaProvider.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.api.dependencies import get_llm_provider
from app.api.models.requests import AnalyzeRequest
from app.infrastructure.providers.llm_ollama import OllamaProvider
from app.infrastructure.providers.llm_openai import OpenAIProvider

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_request(api_key: str = "") -> MagicMock:
    """Build a minimal mock FastAPI Request with a configured X-OpenAI-Key header."""
    request = MagicMock()
    request.headers.get.return_value = api_key
    request.app.state.llm_semaphore = asyncio.Semaphore(1)
    return request


# ── Ticker validation ──────────────────────────────────────────────────────────


@pytest.mark.unit()
class TestTickerValidation:
    def test_xss_script_tag_rejected(self) -> None:
        """<script>alert(1)</script> must fail validation (HTTP 422)."""
        with pytest.raises(ValidationError):
            AnalyzeRequest(ticker="<script>alert(1)</script>")

    def test_path_traversal_rejected(self) -> None:
        """../etc/passwd must fail validation (HTTP 422)."""
        with pytest.raises(ValidationError):
            AnalyzeRequest(ticker="../etc/passwd")

    def test_sql_injection_rejected(self) -> None:
        """' OR '1'='1 must fail validation (HTTP 422)."""
        with pytest.raises(ValidationError):
            AnalyzeRequest(ticker="' OR '1'='1")

    def test_valid_ticker_with_exchange_suffix_accepted(self) -> None:
        """AAPL.L is a valid London-listed ticker — must pass validation (HTTP 202)."""
        req = AnalyzeRequest(ticker="AAPL.L")
        assert req.ticker == "AAPL.L"

    def test_digit_only_ticker_rejected(self) -> None:
        """Digit-only strings are not valid ticker symbols."""
        with pytest.raises(ValidationError):
            AnalyzeRequest(ticker="12345")

    def test_ticker_exceeding_max_length_rejected(self) -> None:
        """Strings longer than 5 base characters + optional 1-dot + 3 chars are rejected."""
        with pytest.raises(ValidationError):
            AnalyzeRequest(ticker="TOOLONGSTR")

    def test_lowercase_ticker_is_uppercased_and_accepted(self) -> None:
        """The before-validator uppercases input; 'aapl' should normalise to 'AAPL'."""
        req = AnalyzeRequest(ticker="aapl")
        assert req.ticker == "AAPL"

    def test_ticker_with_spaces_stripped_and_accepted(self) -> None:
        """Leading/trailing whitespace is stripped before format validation."""
        req = AnalyzeRequest(ticker="  MSFT  ")
        assert req.ticker == "MSFT"


# ── X-OpenAI-Key header guard ──────────────────────────────────────────────────


@pytest.mark.unit()
class TestOpenAIKeyHeaderGuard:
    def test_valid_sk_prefix_key_uses_openai_provider(self) -> None:
        """A well-formed key (starts with sk-, ≤ 200 chars) selects OpenAIProvider."""
        request = _make_request(api_key="sk-validkey1234567890")
        provider = get_llm_provider(request)
        assert isinstance(provider, OpenAIProvider)

    def test_missing_sk_prefix_uses_ollama(self) -> None:
        """A key without the sk- prefix silently falls back to OllamaProvider."""
        request = _make_request(api_key="invalid-key-no-prefix")
        provider = get_llm_provider(request)
        assert isinstance(provider, OllamaProvider)

    def test_empty_key_uses_ollama(self) -> None:
        """An absent header (empty string) selects OllamaProvider."""
        request = _make_request(api_key="")
        provider = get_llm_provider(request)
        assert isinstance(provider, OllamaProvider)

    def test_openai_key_over_200_chars_uses_ollama(self) -> None:
        """A key longer than 200 characters silently falls back to OllamaProvider."""
        long_key = "sk-" + "a" * 200  # 203 characters total — exceeds the 200-char limit
        request = _make_request(api_key=long_key)
        provider = get_llm_provider(request)
        assert isinstance(provider, OllamaProvider)

    def test_openai_key_exactly_200_chars_uses_openai(self) -> None:
        """A key of exactly 200 characters with sk- prefix is accepted."""
        exact_key = "sk-" + "a" * 197  # 200 characters total — at the limit
        request = _make_request(api_key=exact_key)
        provider = get_llm_provider(request)
        assert isinstance(provider, OpenAIProvider)
