from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Database ──────────────────────────────────────────────
    database_url: str

    # ── Redis ─────────────────────────────────────────────────
    redis_url: str

    # ── OPENAI LLM ────────────────────────────────────────────
    openai_model: str = "gpt-4o-mini"

    # ── NVIDIA LLM ────────────────────────────────────────────
    nvidia_api_key: str

    # Fixed allowed models
    nvidia_model_llama: str = "meta/llama-3.1-8b-instruct"
    nvidia_model_mistral: str = "mistralai/mistral-7b-instruct-v0.3"
    nvidia_model_deepseek: str = "deepseek-ai/deepseek-r1-distill-llama-8b"

    # ── Ollama LLM ────────────────────────────────────────────
    ollama_url: str
    default_llm_model: str = "mistral:7b-instruct"

    # ── Pipeline tuning ───────────────────────────────────────
    max_concurrent_llm_calls: int = 5
    pipeline_timeout_seconds: int = 900
    max_articles_per_run: int = 7
    news_window_days: int = 60

    # ── Rate limiting ─────────────────────────────────────────
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60

    # ── Market data providers ─────────────────────────────────
    alpha_vantage_api_key: str

    # ── Data retention ────────────────────────────────────────
    run_retention_hours: int = 24

    # ── Application ───────────────────────────────────────────
    environment: str = "development"
    log_level: str = "INFO"
    app_version: str = "1.0.0"

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins string into list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
