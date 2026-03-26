# backend/Dockerfile
#
# Build targets:
#   base        — shared system packages layer
#   development — editable install with dev extras; hot-reload via uvicorn --reload
#   builder     — production deps only, installed to /install prefix
#   production  — minimal runtime image, non-root user, uvloop + httptools
#
# Why --workers 1 in production CMD:
#   The application stores connection pools, LLM semaphores, and the pipeline
#   orchestrator on app.state, which is NOT shared across Uvicorn worker
#   processes. Using multiple workers would give each worker its own
#   LLM semaphore (allowing workers × 3 concurrent LLM calls), overloading
#   the Ollama server. For horizontal scale-out, run multiple container
#   replicas behind a load balancer — each container is stateless at the HTTP
#   level; all shared state lives in Redis and PostgreSQL.

FROM python:3.11-slim AS base

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ── Development target ─────────────────────────────────────────────────────────
FROM base AS development

COPY pyproject.toml .
RUN pip install -e ".[dev]"

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ── Production builder ─────────────────────────────────────────────────────────
FROM base AS builder

COPY pyproject.toml .
# Install production dependencies only (no dev extras) under /install prefix
RUN pip install --prefix=/install .

COPY app/ ./app/
COPY db/  ./db/

# ── Production target ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS production

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Non-root user — never run production containers as root
RUN groupadd -r stocklens && useradd -r -g stocklens stocklens

# Copy compiled install prefix from builder (no source, no dev deps)
COPY --from=builder /install /usr/local

# Copy only the application and migration directories
COPY --from=builder /app/app ./app
COPY --from=builder /app/db  ./db

RUN chown -R stocklens:stocklens /app

USER stocklens

HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Single worker: see architecture note at top of file
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--loop", "uvloop", "--http", "httptools"]
