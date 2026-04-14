"""NVIDIA NIM (hosted) LLM provider implementation.

Calls NVIDIA hosted API (OpenAI-compatible) at:
  https://integrate.api.nvidia.com/v1/chat/completions

Semaphore is acquired inside complete() — callers never acquire it directly.

Error mapping:
  HTTP 401 → ExternalProviderError(is_retryable=False, error_code="NVIDIA_INVALID_KEY")
  HTTP 429 → ExternalProviderError(is_retryable=True,  error_code="NVIDIA_RATE_LIMITED")
  HTTP 5xx → ExternalProviderError(is_retryable=True,  error_code="NVIDIA_SERVER_ERROR")
"""

from __future__ import annotations

import asyncio

import httpx
import structlog

from app.domain.exceptions import ExternalProviderError

log = structlog.get_logger(__name__)

_CONNECT_TIMEOUT = 5.0  # seconds
_READ_TIMEOUT = 45.0  # seconds (NVIDIA models can be slower)
_NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"


class NvidiaProvider:
    """LLM provider that calls NVIDIA hosted NIM API.

    Uses OpenAI-compatible schema but NVIDIA endpoint.
    Designed for lightweight/free-tier models (e.g. llama, mistral).
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
        """Send prompt to NVIDIA API and return the generated text.

        Raises:
            ExternalProviderError: On HTTP errors or connection failures.
        """
        timeout = httpx.Timeout(
            connect=_CONNECT_TIMEOUT,
            read=_READ_TIMEOUT,
            write=10.0,
            pool=5.0,
        )

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
                        f"{_NVIDIA_BASE_URL}/chat/completions",
                        headers=headers,
                        json=payload,
                    )

                status = response.status_code

                if status == 401:
                    raise ExternalProviderError(
                        "NVIDIA rejected the API key (HTTP 401)",
                        error_code="NVIDIA_INVALID_KEY",
                        user_message="The NVIDIA API key is invalid.",
                        is_retryable=False,
                    )

                if status == 429:
                    raise ExternalProviderError(
                        "NVIDIA rate limit exceeded (HTTP 429)",
                        error_code="NVIDIA_RATE_LIMITED",
                        user_message="Rate limit exceeded. Please retry shortly.",
                        is_retryable=True,
                    )

                if status >= 500:
                    raise ExternalProviderError(
                        f"NVIDIA returned HTTP {status}",
                        error_code="NVIDIA_SERVER_ERROR",
                        user_message="NVIDIA AI service is temporarily unavailable.",
                        is_retryable=True,
                    )

                response.raise_for_status()
                data = response.json()

                return str(data["choices"][0]["message"]["content"])

            except ExternalProviderError:
                raise
            except httpx.ConnectError as exc:
                raise ExternalProviderError(
                    f"Cannot connect to NVIDIA API: {exc}",
                    error_code="NVIDIA_CONNECTION_ERROR",
                    user_message="Cannot reach NVIDIA AI service.",
                    is_retryable=True,
                ) from exc
            except httpx.TimeoutException as exc:
                raise ExternalProviderError(
                    f"NVIDIA request timed out: {exc}",
                    error_code="NVIDIA_TIMEOUT",
                    user_message="NVIDIA AI service took too long to respond.",
                    is_retryable=True,
                ) from exc
            except httpx.HTTPError as exc:
                raise ExternalProviderError(
                    f"NVIDIA HTTP error: {exc}",
                    error_code="NVIDIA_HTTP_ERROR",
                    user_message="Unexpected error communicating with NVIDIA.",
                    is_retryable=True,
                ) from exc
