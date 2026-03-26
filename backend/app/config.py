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
    database_url: str = "postgresql+asyncpg://stocklens:password@localhost:5432/stocklens"

    # ── Redis ─────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── Ollama LLM ────────────────────────────────────────────
    ollama_url: str = "http://localhost:11434"
    default_llm_model: str = "mistral:7b-instruct"

    # ── Pipeline tuning ───────────────────────────────────────
    max_concurrent_llm_calls: int = 2
    pipeline_timeout_seconds: int = 90
    max_articles_per_run: int = 20
    news_window_days: int = 30

    # ── Rate limiting ─────────────────────────────────────────
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60

    # ── Data retention ────────────────────────────────────────
    run_retention_hours: int = 24

    # ── Application ───────────────────────────────────────────
    environment: str = "development"
    log_level: str = "DEBUG"
    app_version: str = "1.0.0"

    # ── Backup (production only) ──────────────────────────────
    backup_encryption_key: str = ""
    backup_s3_bucket: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
