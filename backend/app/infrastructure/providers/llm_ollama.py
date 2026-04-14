"""Ollama LLM provider implementation.

Calls the local Ollama HTTP API (/api/generate) with stream=False.
Semaphore is acquired inside complete() — callers never acquire it directly.
"""

from __future__ import annotations

import asyncio

import httpx
import structlog

from app.domain.exceptions import ExternalProviderError
from app.infrastructure.providers.llm_provider import (
    LLMProvider,  # noqa: F401 (Protocol for type checking)
)

log = structlog.get_logger(__name__)

_CONNECT_TIMEOUT = 5.0  # seconds
_READ_TIMEOUT = 120.0  # seconds — covers model loading on first request


class OllamaProvider:
    """LLM provider that calls a locally-running Ollama server.

    Satisfies the LLMProvider Protocol structurally — no inheritance required.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        semaphore: asyncio.Semaphore,
    ) -> None:
        self._base_url = base_url.rstrip("/")
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
        """Send prompt to Ollama and return the generated text.

        Raises:
            ExternalProviderError: On HTTP 5xx or connection failure.
        """
        timeout = httpx.Timeout(connect=_CONNECT_TIMEOUT, read=_READ_TIMEOUT, write=10.0, pool=5.0)
        payload = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
            },
        }

        async with self._semaphore:
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(
                        f"{self._base_url}/api/generate",
                        json=payload,
                    )

                if response.status_code >= 500:
                    raise ExternalProviderError(
                        f"Ollama returned HTTP {response.status_code}",
                        error_code="OLLAMA_SERVER_ERROR",
                        user_message="The local AI model is not responding. Please try again.",
                        is_retryable=True,
                    )

                response.raise_for_status()
                data = response.json()
                return str(data.get("response", ""))

            except ExternalProviderError:
                raise
            except httpx.ConnectError as exc:
                raise ExternalProviderError(
                    f"Cannot connect to Ollama at {self._base_url}: {exc}",
                    error_code="OLLAMA_CONNECTION_ERROR",
                    user_message="Cannot reach the local AI model. Is Ollama running?",
                    is_retryable=True,
                ) from exc
            except httpx.TimeoutException as exc:
                raise ExternalProviderError(
                    f"Ollama request timed out: {exc}",
                    error_code="OLLAMA_TIMEOUT",
                    user_message="The local AI model took too long to respond.",
                    is_retryable=True,
                ) from exc
            except httpx.HTTPError as exc:
                raise ExternalProviderError(
                    f"Ollama HTTP error: {exc}",
                    error_code="OLLAMA_HTTP_ERROR",
                    user_message="Unexpected error communicating with the local AI model.",
                    is_retryable=True,
                ) from exc
