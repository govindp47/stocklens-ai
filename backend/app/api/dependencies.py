"""FastAPI dependency providers for StockLens AI.

All dependencies are injected via FastAPI's Depends() mechanism.
Stateful objects (DB pool, Redis, orchestrator, semaphore) are stored on
``app.state`` during the lifespan context and retrieved here.

LLM provider selection:
  - X-OpenAI-Key header present and starts with "sk-" → OpenAIProvider
  - Otherwise → OllamaProvider

Both providers satisfy the LLMProvider Protocol.
"""

from __future__ import annotations

import asyncio

import asyncpg
from fastapi import Request
from redis.asyncio import Redis

from app.config import Settings, get_settings
from app.infrastructure.providers.llm_nvidia import NvidiaProvider
from app.infrastructure.providers.llm_ollama import OllamaProvider
from app.infrastructure.providers.llm_openai import OpenAIProvider
from app.infrastructure.providers.prompt_loader import PromptLoader
from app.pipeline.orchestrator import PipelineOrchestrator

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


def get_prompt_loader(request: Request) -> PromptLoader:
    """Return the singleton PromptLoader created during app startup."""
    loader: PromptLoader = request.app.state.prompt_loader
    return loader


def get_orchestrator(request: Request) -> PipelineOrchestrator:
    """Return the singleton PipelineOrchestrator created during app startup."""
    orchestrator: PipelineOrchestrator = request.app.state.orchestrator
    return orchestrator


def get_llm_provider(
    request: Request,
) -> OllamaProvider | OpenAIProvider | NvidiaProvider:
    """Select LLM provider based on request headers.

    Priority:
      1. OpenAI → if X-OpenAI-Key provided
      2. NVIDIA → based on X-LLM-Provider header (predefined models)
      3. Default → Ollama

    NVIDIA API key is always loaded from environment.

    If the header is present and starts with ``sk-``, an OpenAI provider is
    returned.  Otherwise other provider are used.

    Security note: the key is validated for format only (``sk-`` prefix and
    ≤ 200 characters).  No cryptographic verification is performed — the key
    is forwarded verbatim to the OpenAI API.  Invalid keys will fail at
    inference time.
    """
    settings: Settings = get_settings()
    semaphore: asyncio.Semaphore = request.app.state.llm_semaphore

    openai_key = request.headers.get("X-OpenAI-Key", "")
    provider_hint = request.headers.get("X-LLM-Provider", "").lower()

    # ── OpenAI (user provided key) ────────────────────────────
    if openai_key and openai_key.startswith("sk-") and len(openai_key) <= 200:
        return OpenAIProvider(
            api_key=openai_key,
            model=settings.openai_model,
            semaphore=semaphore,
        )

    # ── NVIDIA (env key, fixed models) ────────────────────────
    nvidia_key = settings.nvidia_api_key

    if provider_hint == "nvidia-llama":
        return NvidiaProvider(
            api_key=nvidia_key,
            model=settings.nvidia_model_llama,
            semaphore=semaphore,
        )

    if provider_hint == "nvidia-mistral":
        return NvidiaProvider(
            api_key=nvidia_key,
            model=settings.nvidia_model_mistral,
            semaphore=semaphore,
        )

    if provider_hint == "nvidia-deepseek":
        return NvidiaProvider(
            api_key=nvidia_key,
            model=settings.nvidia_model_deepseek,
            semaphore=semaphore,
        )

    # ── Default fallback → Ollama ─────────────────────────────
    return OllamaProvider(
        base_url=settings.ollama_url,
        model=settings.default_llm_model,
        semaphore=semaphore,
    )


# Re-exported so callers can use `from app.api.dependencies import get_settings`
__all__ = [
    "get_db_pool",
    "get_redis",
    "get_llm_semaphore",
    "get_orchestrator",
    "get_llm_provider",
    "get_prompt_loader",
    "get_settings",
    "OllamaProvider",
    "OpenAIProvider",
    "NvidiaProvider",
    "PromptLoader",
    "Settings",
]
