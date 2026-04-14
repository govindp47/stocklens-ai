"""OpenAI-compatible LLM provider implementation.

Calls the OpenAI /v1/chat/completions endpoint with Bearer auth.
Semaphore is acquired inside complete() — callers never acquire it directly.

Error code mapping:
  HTTP 401 → ExternalProviderError(is_retryable=False, error_code="OPENAI_INVALID_KEY")
  HTTP 429 → ExternalProviderError(is_retryable=True,  error_code="OPENAI_RATE_LIMITED")
  HTTP 5xx → ExternalProviderError(is_retryable=True,  error_code="OPENAI_SERVER_ERROR")
"""

from __future__ import annotations

import asyncio

import httpx
import structlog

from app.domain.exceptions import ExternalProviderError

log = structlog.get_logger(__name__)

_CONNECT_TIMEOUT = 5.0  # seconds
_READ_TIMEOUT = 30.0  # seconds
_OPENAI_BASE_URL = "https://api.openai.com"


class OpenAIProvider:
    """LLM provider that calls the OpenAI chat completions API.

    Satisfies the LLMProvider Protocol structurally — no inheritance required.
    The API key is held only for the lifetime of the provider instance (per-request).
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        semaphore: asyncio.Semaphore,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._semaphore = semaphore

    @property
    def model_name(self) -> str:
        return self._model

    async def complete(
        self,
        prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.1,
    ) -> str:
        """Send prompt to OpenAI and return the generated text.

        Raises:
            ExternalProviderError: On HTTP 401, 429, 5xx, or connection failure.
        """
        timeout = httpx.Timeout(connect=_CONNECT_TIMEOUT, read=_READ_TIMEOUT, write=10.0, pool=5.0)
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        async with self._semaphore:
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(
                        f"{_OPENAI_BASE_URL}/v1/chat/completions",
                        headers=headers,
                        json=payload,
                    )

                status = response.status_code

                if status == 401:
                    raise ExternalProviderError(
                        "OpenAI rejected the API key (HTTP 401)",
                        error_code="OPENAI_INVALID_KEY",
                        user_message="The OpenAI API key is invalid or has been revoked.",
                        is_retryable=False,
                    )

                if status == 429:
                    raise ExternalProviderError(
                        "OpenAI rate limit exceeded (HTTP 429)",
                        error_code="OPENAI_RATE_LIMITED",
                        user_message="OpenAI rate limit reached. Please wait and try again.",
                        is_retryable=True,
                    )

                if status >= 500:
                    raise ExternalProviderError(
                        f"OpenAI returned HTTP {status}",
                        error_code="OPENAI_SERVER_ERROR",
                        user_message="OpenAI is currently unavailable. Please try again later.",
                        is_retryable=True,
                    )

                response.raise_for_status()
                data = response.json()
                return str(data["choices"][0]["message"]["content"])

            except ExternalProviderError:
                raise
            except httpx.ConnectError as exc:
                raise ExternalProviderError(
                    f"Cannot connect to OpenAI: {exc}",
                    error_code="OPENAI_CONNECTION_ERROR",
                    user_message="Cannot reach OpenAI. Check your network connection.",
                    is_retryable=True,
                ) from exc
            except httpx.TimeoutException as exc:
                raise ExternalProviderError(
                    f"OpenAI request timed out: {exc}",
                    error_code="OPENAI_TIMEOUT",
                    user_message="OpenAI took too long to respond.",
                    is_retryable=True,
                ) from exc
            except httpx.HTTPError as exc:
                raise ExternalProviderError(
                    f"OpenAI HTTP error: {exc}",
                    error_code="OPENAI_HTTP_ERROR",
                    user_message="Unexpected error communicating with OpenAI.",
                    is_retryable=True,
                ) from exc
