"""FastAPI dependency providers for StockLens AI.

All dependencies are injected via FastAPI's Depends() mechanism.
Stateful objects (DB pool, Redis, orchestrator, semaphore) are stored on
``app.state`` during the lifespan context and retrieved here.

LLM provider selection:
  - X-OpenAI-Key header present and starts with "sk-" → OpenAIProviderStub
  - Otherwise → OllamaProviderStub

Both stubs satisfy the LLMProvider Protocol.  Full implementations are in T-031.
"""

from __future__ import annotations

import asyncio

import asyncpg
from fastapi import Request
from redis.asyncio import Redis

from app.config import Settings, get_settings
from app.pipeline.orchestrator import PipelineOrchestrator


# ── LLM provider stubs (T-031 will replace with full implementations) ──────────


class OllamaProviderStub:
    """Placeholder Ollama provider satisfying LLMProvider Protocol.

    Used when no X-OpenAI-Key header is present.  T-031 replaces this with a
    full implementation that calls the local Ollama HTTP API.
    """

    @property
    def model_name(self) -> str:
        return "ollama"

    async def complete(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        raise NotImplementedError("OllamaProvider not yet implemented (T-031)")


class OpenAIProviderStub:
    """Placeholder OpenAI provider satisfying LLMProvider Protocol.

    Used when the X-OpenAI-Key header is present with a valid ``sk-`` prefix.
    T-031 replaces this with a full implementation that calls the OpenAI API.

    The API key is held only for the duration of the request and is never
    logged, stored, or returned in any response.
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    @property
    def model_name(self) -> str:
        return "openai"

    async def complete(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        raise NotImplementedError("OpenAIProvider not yet implemented (T-031)")


# ── Core state dependencies ────────────────────────────────────────────────────


def get_db_pool(request: Request) -> asyncpg.Pool:
    pool: asyncpg.Pool = request.app.state.db_pool
    return pool


def get_redis(request: Request) -> Redis:  # type: ignore[type-arg]
    client: Redis[str] = request.app.state.redis
    return client


def get_llm_semaphore(request: Request) -> asyncio.Semaphore:
    semaphore: asyncio.Semaphore = request.app.state.llm_semaphore
    return semaphore


# ── Pipeline dependencies ──────────────────────────────────────────────────────


def get_orchestrator(request: Request) -> PipelineOrchestrator:
    """Return the singleton PipelineOrchestrator created during app startup."""
    orchestrator: PipelineOrchestrator = request.app.state.orchestrator
    return orchestrator


def get_llm_provider(
    request: Request,
) -> OllamaProviderStub | OpenAIProviderStub:
    """Select LLM provider based on the X-OpenAI-Key request header.

    If the header is present and starts with ``sk-``, an OpenAI provider is
    returned.  Otherwise the default Ollama provider is used.

    Security note: the key is validated for format only (``sk-`` prefix).
    No cryptographic verification is performed — the key is forwarded
    verbatim to the OpenAI API.  Invalid keys will fail at inference time.
    """
    api_key = request.headers.get("X-OpenAI-Key", "")
    if api_key and api_key.startswith("sk-"):
        return OpenAIProviderStub(api_key)
    return OllamaProviderStub()


# Re-exported so callers can use `from app.api.dependencies import get_settings`
__all__ = [
    "get_db_pool",
    "get_redis",
    "get_llm_semaphore",
    "get_orchestrator",
    "get_llm_provider",
    "get_settings",
    "OllamaProviderStub",
    "OpenAIProviderStub",
    "Settings",
]
