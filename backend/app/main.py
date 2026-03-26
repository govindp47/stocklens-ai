from __future__ import annotations

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

import app.metrics as _metrics  # noqa: F401 — registers Prometheus metrics on import
from app.api.routers import health
from app.config import get_settings
from app.lifespan import lifespan
from app.logging_config import configure_logging


def create_app() -> FastAPI:
    configure_logging(get_settings().log_level)

    application = FastAPI(
        title="StockLens AI",
        description="AI-powered stock analysis API",
        version="1.0.0",
        lifespan=lifespan,
    )

    application.include_router(health.router)

    # Expose /metrics for Prometheus scraping (blocked externally by Nginx)
    Instrumentator().instrument(application).expose(
        application,
        endpoint="/metrics",
        include_in_schema=False,
    )

    return application


app: FastAPI = create_app()
