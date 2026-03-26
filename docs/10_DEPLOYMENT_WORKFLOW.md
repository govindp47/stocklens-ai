# 10_DEPLOYMENT_WORKFLOW.md — StockLens AI

---

## 1. Development Environment Setup

### Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| Docker Desktop | 4.28+ | Container runtime for all services |
| Docker Compose | 2.24+ | Local multi-service orchestration |
| Python | 3.11+ | Backend development |
| Node.js | 20 LTS | Frontend development |
| Git | 2.40+ | Version control |
| `make` | Any | Convenience command runner |

### First-Time Setup Script

```bash
#!/usr/bin/env bash
# scripts/dev-setup.sh

set -euo pipefail

echo "==> Checking prerequisites..."
command -v docker   >/dev/null || { echo "Docker is not installed"; exit 1; }
command -v python3  >/dev/null || { echo "Python 3.11+ is required"; exit 1; }
command -v node     >/dev/null || { echo "Node.js 20+ is required"; exit 1; }

echo "==> Copying environment files..."
cp backend/.env.example backend/.env
cp frontend/.env.local.example frontend/.env.local

echo "==> Installing Python dependencies (editable mode)..."
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]" --quiet

echo "==> Installing Node.js dependencies..."
cd ../frontend
npm ci --silent

echo "==> Building Docker images..."
cd ..
docker compose -f infra/docker-compose.yml build

echo "==> Starting infrastructure containers (DB, Redis, Ollama)..."
docker compose -f infra/docker-compose.yml up -d db redis ollama

echo "==> Waiting for PostgreSQL to be ready..."
until docker compose exec db pg_isready -U stocklens -q; do
  sleep 1
done

echo "==> Running database migrations..."
cd backend
source .venv/bin/activate
alembic upgrade head

echo "==> Pulling Ollama model (this may take several minutes)..."
docker compose exec ollama ollama pull mistral:7b-instruct

echo ""
echo "Setup complete. Run 'make dev' to start all services."
```

### `Makefile` — Developer Commands

```makefile
.PHONY: dev dev-backend dev-frontend test test-unit test-integration \
        migrate lint typecheck clean logs

# Start full local stack
dev:
 docker compose -f infra/docker-compose.yml up

# Start only backend services (DB, Redis, Ollama) + FastAPI with hot-reload
dev-backend:
 docker compose -f infra/docker-compose.yml up -d db redis ollama
 cd backend && source .venv/bin/activate && \
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Start only Next.js dev server
dev-frontend:
 cd frontend && npm run dev

# Run all tests
test:
 make test-unit && make test-integration

# Unit tests only (no Docker required)
test-unit:
 cd backend && source .venv/bin/activate && \
   pytest tests/unit -m unit -v

# Integration tests (requires running DB + Redis)
test-integration:
 docker compose -f infra/docker-compose.test.yml up -d
 cd backend && source .venv/bin/activate && \
   TEST_DATABASE_URL=postgresql://stocklens:test@localhost:5433/stocklens_test \
   pytest tests/integration -m integration -v
 docker compose -f infra/docker-compose.test.yml down

# Database migration
migrate:
 cd backend && source .venv/bin/activate && alembic upgrade head

# Linting
lint:
 cd backend && source .venv/bin/activate && ruff check app tests
 cd frontend && npx eslint .

# Type checking
typecheck:
 cd backend && source .venv/bin/activate && mypy app --strict
 cd frontend && npx tsc --noEmit

# Tail logs for all services
logs:
 docker compose -f infra/docker-compose.yml logs -f api frontend

# Remove all containers, volumes, and build artifacts
clean:
 docker compose -f infra/docker-compose.yml down -v --remove-orphans
 find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
 find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
 cd frontend && rm -rf .next node_modules
```

---

## 2. Docker Compose — Local Development

```yaml
# infra/docker-compose.yml
version: '3.9'

services:
  api:
    build:
      context: ../backend
      dockerfile: Dockerfile
      target: development
    ports:
      - "8000:8000"
    volumes:
      - ../backend/app:/app/app:ro    # hot-reload via uvicorn --reload
      - ../backend/db:/app/db:ro
    environment:
      - DATABASE_URL=postgresql+asyncpg://stocklens:password@db:5432/stocklens
      - REDIS_URL=redis://redis:6379/0
      - OLLAMA_URL=http://ollama:11434
      - DEFAULT_LLM_MODEL=mistral:7b-instruct
      - ENVIRONMENT=development
      - LOG_LEVEL=DEBUG
      - MAX_CONCURRENT_LLM_CALLS=2
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - stocklens_internal

  frontend:
    build:
      context: ../frontend
      dockerfile: Dockerfile
      target: development
    ports:
      - "3000:3000"
    volumes:
      - ../frontend:/app:ro
      - /app/node_modules           # prevent host node_modules override
      - /app/.next                  # prevent host .next override
    environment:
      - NEXT_PUBLIC_API_URL=http://localhost:8000
      - NODE_ENV=development
    networks:
      - stocklens_internal

  db:
    image: postgres:15-alpine
    ports:
      - "5432:5432"
    environment:
      - POSTGRES_DB=stocklens
      - POSTGRES_USER=stocklens
      - POSTGRES_PASSWORD=password
    volumes:
      - pg_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U stocklens"]
      interval: 5s
      timeout: 3s
      retries: 10
    networks:
      - stocklens_internal

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    command: redis-server --save "" --appendonly no   # no persistence in dev
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10
    networks:
      - stocklens_internal

  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_models:/root/.ollama
    environment:
      - OLLAMA_NUM_PARALLEL=2
      - OLLAMA_MAX_LOADED_MODELS=1
      - OLLAMA_KEEP_ALIVE=10m
    networks:
      - stocklens_internal

  prometheus:
    image: prom/prometheus:v2.50.0
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus_data:/prometheus
    networks:
      - stocklens_internal

  grafana:
    image: grafana/grafana:10.3.0
    ports:
      - "3001:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_USERS_ALLOW_SIGN_UP=false
    volumes:
      - grafana_data:/var/lib/grafana
      - ./monitoring/grafana/dashboards:/etc/grafana/provisioning/dashboards:ro
    depends_on:
      - prometheus
    networks:
      - stocklens_internal

  loki:
    image: grafana/loki:2.9.0
    ports:
      - "3100:3100"
    volumes:
      - ./monitoring/loki/loki-config.yml:/etc/loki/local-config.yaml:ro
      - loki_data:/loki
    networks:
      - stocklens_internal

  promtail:
    image: grafana/promtail:2.9.0
    volumes:
      - /var/lib/docker/containers:/var/lib/docker/containers:ro
      - /var/run/docker.sock:/var/run/docker.sock
      - ./monitoring/loki/promtail-config.yml:/etc/promtail/config.yml:ro
    depends_on:
      - loki
    networks:
      - stocklens_internal

volumes:
  pg_data:
  ollama_models:
  prometheus_data:
  grafana_data:
  loki_data:

networks:
  stocklens_internal:
    driver: bridge
```

---

## 3. Docker Image Definitions

### Backend Dockerfile

```dockerfile
# backend/Dockerfile
FROM python:3.11-slim AS base

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ── Development target ────────────────────────────────────────
FROM base AS development

COPY pyproject.toml .
RUN pip install -e ".[dev]"

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ── Production builder ────────────────────────────────────────
FROM base AS builder

COPY pyproject.toml .
RUN pip install --prefix=/install .

COPY app/ ./app/
COPY db/  ./db/

# ── Production target ─────────────────────────────────────────
FROM python:3.11-slim AS production

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Non-root user
RUN groupadd -r stocklens && useradd -r -g stocklens stocklens

COPY --from=builder /install /usr/local
COPY --from=builder /app/app  ./app
COPY --from=builder /app/db   ./db

RUN chown -R stocklens:stocklens /app
USER stocklens

HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--loop", "uvloop", "--http", "httptools"]
```

**Why `--workers 1`:** A single Uvicorn worker is used because:

1. The application uses `app.state` (connection pools, semaphores) that are not safe to share across workers.
2. Multiple workers would each have their own LLM semaphore, allowing `workers × 3` concurrent LLM calls — more than the Ollama server can handle.
3. For multi-worker scale-out, use multiple container replicas behind a load balancer instead. Each container is stateless at the HTTP level; shared state is in Redis.

### Frontend Dockerfile

```dockerfile
# frontend/Dockerfile
FROM node:20-alpine AS base
WORKDIR /app

# ── Dependencies ──────────────────────────────────────────────
FROM base AS deps
COPY package.json package-lock.json ./
RUN npm ci --frozen-lockfile

# ── Development ───────────────────────────────────────────────
FROM base AS development
COPY --from=deps /app/node_modules ./node_modules
COPY . .
CMD ["npm", "run", "dev"]

# ── Builder ───────────────────────────────────────────────────
FROM base AS builder
COPY --from=deps /app/node_modules ./node_modules
COPY . .

ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN npm run build

# ── Production ────────────────────────────────────────────────
FROM node:20-alpine AS production
WORKDIR /app
ENV NODE_ENV=production

RUN addgroup -S stocklens && adduser -S stocklens -G stocklens

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static     ./.next/static
COPY --from=builder /app/public           ./public

RUN chown -R stocklens:stocklens /app
USER stocklens

EXPOSE 3000
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=3 \
  CMD wget -qO- http://localhost:3000/api/health || exit 1

CMD ["node", "server.js"]
```

**`standalone` output mode:** `next.config.ts` must include `output: 'standalone'` to enable the minimal server.js output that does not bundle `node_modules` in the final image layer.

---

## 4. Nginx Configuration — Production

```nginx
# infra/nginx/nginx.conf

user  nginx;
worker_processes  auto;
error_log  /var/log/nginx/error.log warn;

events {
    worker_connections 1024;
}

http {
    # ── Rate limiting zones ──────────────────────────────────
    limit_req_zone  $binary_remote_addr zone=api_analyze:10m rate=20r/m;
    limit_req_zone  $binary_remote_addr zone=api_general:10m rate=120r/m;
    limit_conn_zone $binary_remote_addr zone=conn_per_ip:10m;

    # ── Upstream definitions ─────────────────────────────────
    upstream api_upstream {
        server api:8000;
        keepalive 16;
    }

    upstream frontend_upstream {
        server frontend:3000;
        keepalive 8;
    }

    # ── HTTP → HTTPS redirect ────────────────────────────────
    server {
        listen 80;
        server_name _;
        return 301 https://$host$request_uri;
    }

    # ── HTTPS server ─────────────────────────────────────────
    server {
        listen 443 ssl http2;
        server_name stocklens.example.com;

        ssl_certificate     /etc/nginx/ssl/fullchain.pem;
        ssl_certificate_key /etc/nginx/ssl/privkey.pem;
        ssl_protocols       TLSv1.2 TLSv1.3;
        ssl_ciphers         ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:
                            ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
        ssl_prefer_server_ciphers off;
        ssl_session_cache   shared:SSL:10m;
        ssl_session_timeout 1d;
        ssl_session_tickets off;

        # ── Security headers ─────────────────────────────────
        add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
        add_header X-Content-Type-Options    "nosniff" always;
        add_header X-Frame-Options           "DENY" always;
        add_header X-XSS-Protection          "1; mode=block" always;
        add_header Referrer-Policy           "strict-origin-when-cross-origin" always;
        add_header Content-Security-Policy   "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; frame-src 'none'; object-src 'none';" always;

        # ── Block internal endpoints ─────────────────────────
        location /metrics {
            deny all;
            return 404;
        }

        location /health {
            allow 127.0.0.1;
            allow 172.16.0.0/12;
            deny all;
            proxy_pass http://api_upstream/health;
        }

        # ── API routes ───────────────────────────────────────
        location /api/v1/analyze {
            limit_req  zone=api_analyze burst=5 nodelay;
            limit_conn conn_per_ip 10;

            # SSE-specific: disable buffering
            proxy_buffering          off;
            proxy_cache              off;
            proxy_read_timeout       120s;    # > pipeline_timeout(90s) + buffer

            proxy_pass               http://api_upstream;
            proxy_set_header         Host              $host;
            proxy_set_header         X-Real-IP         $remote_addr;
            proxy_set_header         X-Forwarded-For   $proxy_add_x_forwarded_for;
            proxy_set_header         X-Forwarded-Proto $scheme;
            proxy_http_version       1.1;
            proxy_set_header         Connection "";    # keepalive
        }

        location /api/ {
            limit_req  zone=api_general burst=20 nodelay;
            limit_conn conn_per_ip 20;

            proxy_pass               http://api_upstream;
            proxy_set_header         Host              $host;
            proxy_set_header         X-Real-IP         $remote_addr;
            proxy_set_header         X-Forwarded-For   $proxy_add_x_forwarded_for;
            proxy_set_header         X-Forwarded-Proto $scheme;
            proxy_http_version       1.1;
            proxy_set_header         Connection "";
            proxy_read_timeout       30s;
        }

        # ── Frontend routes ──────────────────────────────────
        location /_next/static/ {
            proxy_pass http://frontend_upstream;
            expires    1y;
            add_header Cache-Control "public, immutable";
        }

        location / {
            proxy_pass               http://frontend_upstream;
            proxy_set_header         Host              $host;
            proxy_set_header         X-Real-IP         $remote_addr;
            proxy_set_header         X-Forwarded-For   $proxy_add_x_forwarded_for;
            proxy_http_version       1.1;
            proxy_set_header         Connection "";
        }

        # ── Request size limits ──────────────────────────────
        client_max_body_size   1k;
        client_body_timeout    10s;
        client_header_timeout  10s;
        send_timeout           10s;
    }
}
```

**SSE proxy configuration notes:**

- `proxy_buffering off` is mandatory for SSE. Nginx's default response buffering would hold SSE events in a buffer until the buffer fills before flushing to the client — destroying the real-time delivery guarantee.
- `proxy_read_timeout 120s` must exceed the maximum pipeline duration (90s) plus connection establishment time.
- The `X-Accel-Buffering: no` header sent by the FastAPI `StreamingResponse` provides a redundant signal to Nginx to disable buffering even if `proxy_buffering` is accidentally omitted.

---

## 5. CI/CD Architecture

### GitHub Actions Pipeline

```
┌─────────────────────────────────────────────────────────────────────┐
│  TRIGGER: push to any branch / pull request                         │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
            ┌─────────────────┼──────────────────────┐
            ▼                 ▼                       ▼
   ┌─────────────────┐ ┌───────────────┐ ┌─────────────────────┐
   │ backend-lint    │ │ frontend-lint │ │ security-audit      │
   │ • ruff check    │ │ • eslint      │ │ • pip-audit         │
   │ • mypy --strict │ │ • tsc noEmit  │ │ • npm audit         │
   └────────┬────────┘ └──────┬────────┘ └──────────┬──────────┘
            │                 │                      │
            ▼                 ▼                      │
   ┌─────────────────┐ ┌───────────────┐             │
   │ backend-unit    │ │ frontend-unit │             │
   │ pytest -m unit  │ │ vitest run    │             │
   └────────┬────────┘ └──────┬────────┘             │
            │                 │                      │
            └────────┬────────┘                      │
                     ▼                               │
          ┌──────────────────────┐                   │
          │ backend-integration  │                   │
          │ (postgres + redis    │                   │
          │  GitHub services)    │                   │
          └──────────┬───────────┘                   │
                     │                               │
                     └──────────────┬────────────────┘
                                    ▼
                         ┌──────────────────┐
                         │   build-images   │
                         │ docker buildx    │
                         │ • api:${sha}     │
                         │ • frontend:${sha}│
                         └────────┬─────────┘
                                  │
               ┌──────────────────┼──────────────────┐
               │ (only on main)   │                  │
               ▼                  ▼                  ▼
     ┌──────────────┐   ┌──────────────┐   ┌──────────────────┐
     │ push-images  │   │  e2e-tests   │   │  deploy-staging  │
     │ to GHCR      │   │  Playwright  │   │  (if configured) │
     └──────────────┘   └──────────────┘   └──────────────────┘
                                                    │
                                    ┌───────────────┘
                                    │ (manual approval gate)
                                    ▼
                           ┌────────────────┐
                           │ deploy-prod    │
                           │ SSH + compose  │
                           └────────────────┘
```

### Complete CI Workflow File

```yaml
# .github/workflows/ci.yml
name: CI/CD Pipeline

on:
  push:
    branches: ['**']
  pull_request:
    branches: [main]

env:
  REGISTRY: ghcr.io
  IMAGE_PREFIX: ${{ github.repository_owner }}/stocklens

jobs:
  backend-lint:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'
      - run: pip install -e ".[dev]" -q
      - run: ruff check app tests
      - run: ruff format --check app tests
      - run: mypy app --strict

  frontend-lint:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci --silent
      - run: npx tsc --noEmit
      - run: npx eslint . --max-warnings 0
      - run: npx prettier --check .

  security-audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install pip-audit -q
      - run: pip-audit -r backend/requirements.txt --vulnerability-service pypi
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - run: cd frontend && npm audit --audit-level=high

  backend-unit:
    runs-on: ubuntu-latest
    needs: [backend-lint]
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'
      - run: pip install -e ".[dev]" -q
      - run: pytest tests/unit -m unit -v --cov=app --cov-report=xml --cov-fail-under=80
      - uses: codecov/codecov-action@v4
        with:
          files: backend/coverage.xml

  frontend-unit:
    runs-on: ubuntu-latest
    needs: [frontend-lint]
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci --silent
      - run: npx vitest run --coverage

  backend-integration:
    runs-on: ubuntu-latest
    needs: [backend-unit]
    services:
      postgres:
        image: postgres:15-alpine
        env:
          POSTGRES_DB: stocklens_test
          POSTGRES_USER: stocklens
          POSTGRES_PASSWORD: test_password
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 5s
          --health-timeout 3s
          --health-retries 10
      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 5s
          --health-timeout 3s
          --health-retries 10
    env:
      TEST_DATABASE_URL: postgresql://stocklens:test_password@localhost:5432/stocklens_test
      REDIS_URL: redis://localhost:6379/0
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'
      - run: pip install -e ".[dev]" -q
      - run: alembic upgrade head
      - run: pytest tests/integration -m integration -v

  build-images:
    runs-on: ubuntu-latest
    needs: [backend-integration, frontend-unit, security-audit]
    outputs:
      api-tag:      ${{ steps.meta-api.outputs.tags }}
      frontend-tag: ${{ steps.meta-frontend.outputs.tags }}
      digest-api:   ${{ steps.build-api.outputs.digest }}
    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract metadata — API
        id: meta-api
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_PREFIX }}-api
          tags: |
            type=sha,prefix=sha-
            type=ref,event=branch
            type=raw,value=latest,enable=${{ github.ref == 'refs/heads/main' }}

      - name: Build and push API image
        id: build-api
        uses: docker/build-push-action@v5
        with:
          context: backend
          file: backend/Dockerfile
          target: production
          push: ${{ github.ref == 'refs/heads/main' }}
          tags: ${{ steps.meta-api.outputs.tags }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Build and push Frontend image
        uses: docker/build-push-action@v5
        with:
          context: frontend
          file: frontend/Dockerfile
          target: production
          push: ${{ github.ref == 'refs/heads/main' }}
          build-args: |
            NEXT_PUBLIC_API_URL=https://stocklens.example.com
          tags: ${{ steps.meta-frontend.outputs.tags }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  e2e:
    runs-on: ubuntu-latest
    needs: [build-images]
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - run: |
          docker compose -f infra/docker-compose.test.yml up -d
          ./scripts/wait-for-healthy.sh   # polls /health endpoints
      - run: cd frontend && npm ci && npx playwright install chromium
      - run: cd frontend && npx playwright test --project=chromium
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: playwright-report
          path: frontend/playwright-report/
      - run: docker compose -f infra/docker-compose.test.yml down

  deploy-production:
    runs-on: ubuntu-latest
    needs: [e2e]
    if: github.ref == 'refs/heads/main'
    environment:
      name: production
      url: https://stocklens.example.com
    steps:
      - uses: actions/checkout@v4

      - name: Deploy to production server
        uses: appleboy/ssh-action@v1.0.3
        with:
          host:     ${{ secrets.PROD_HOST }}
          username: ${{ secrets.PROD_USER }}
          key:      ${{ secrets.PROD_SSH_KEY }}
          script: |
            set -euo pipefail
            cd /opt/stocklens

            # Pull latest images
            echo "${{ secrets.GHCR_TOKEN }}" | docker login ghcr.io -u ${{ github.actor }} --password-stdin
            docker compose -f infra/docker-compose.prod.yml pull api frontend

            # Run migrations before bringing up new containers
            docker compose -f infra/docker-compose.prod.yml run --rm api alembic upgrade head

            # Rolling replacement: bring up new api and frontend, keep db/redis/ollama running
            docker compose -f infra/docker-compose.prod.yml up -d --no-deps api frontend

            # Health check
            sleep 10
            curl -sf http://localhost:8000/health || { echo "API health check failed"; exit 1; }
            curl -sf http://localhost:3000/api/health || { echo "Frontend health check failed"; exit 1; }

            echo "Deployment successful: $(date -u)"
```

---

## 6. Environment Configurations

### Environment Variable Matrix

| Variable | Development | Test | Production |
|---|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://stocklens:password@db:5432/stocklens` | `postgresql+asyncpg://stocklens:test@localhost:5432/stocklens_test` | Secret (GHCR/host secret) |
| `REDIS_URL` | `redis://redis:6379/0` | `redis://localhost:6379/1` | Secret |
| `OLLAMA_URL` | `http://ollama:11434` | Not used (mocked) | `http://ollama:11434` |
| `DEFAULT_LLM_MODEL` | `mistral:7b-instruct` | N/A | `mistral:7b-instruct` |
| `ENVIRONMENT` | `development` | `test` | `production` |
| `LOG_LEVEL` | `DEBUG` | `WARNING` | `INFO` |
| `MAX_CONCURRENT_LLM_CALLS` | `2` | N/A | `3` |
| `PIPELINE_TIMEOUT_SECONDS` | `90` | `10` | `90` |
| `MAX_ARTICLES_PER_RUN` | `20` | `5` | `20` |
| `RATE_LIMIT_REQUESTS` | `100` (relaxed for dev) | `10` | `10` |
| `BACKUP_ENCRYPTION_KEY` | N/A | N/A | Secret |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | `http://localhost:8000` | `https://stocklens.example.com` |

### Production Docker Compose Override

```yaml
# infra/docker-compose.prod.yml
# Applied on top of docker-compose.yml for production

version: '3.9'

services:
  api:
    image: ghcr.io/${REPO_OWNER}/stocklens-api:latest
    restart: unless-stopped
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=${REDIS_URL}
      - OLLAMA_URL=http://ollama:11434
      - ENVIRONMENT=production
      - LOG_LEVEL=INFO
      - MAX_CONCURRENT_LLM_CALLS=3
      - RATE_LIMIT_REQUESTS=10
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 512M

  frontend:
    image: ghcr.io/${REPO_OWNER}/stocklens-frontend:latest
    restart: unless-stopped
    logging:
      driver: json-file
      options:
        max-size: "5m"
        max-file: "3"

  nginx:
    image: nginx:1.25-alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - /etc/letsencrypt/live/stocklens.example.com:/etc/nginx/ssl:ro
    depends_on:
      - api
      - frontend

  db:
    restart: unless-stopped
    volumes:
      - pg_data:/var/lib/postgresql/data
    command: >
      postgres
        -c max_connections=20
        -c shared_buffers=128MB
        -c effective_cache_size=256MB
        -c maintenance_work_mem=32MB
        -c wal_buffers=4MB

  redis:
    restart: unless-stopped
    command: >
      redis-server
        --save 3600 1
        --appendonly yes
        --maxmemory 128mb
        --maxmemory-policy allkeys-lru

  backup:
    image: ghcr.io/${REPO_OWNER}/stocklens-backup:latest
    restart: unless-stopped
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - BACKUP_ENCRYPTION_KEY=${BACKUP_ENCRYPTION_KEY}
      - BACKUP_S3_BUCKET=${BACKUP_S3_BUCKET}
      - ENVIRONMENT=production
    volumes:
      - backup_data:/backups
```

---

## 7. Build Variants

| Variant | Docker Target | Purpose | Notable Differences |
|---|---|---|---|
| `development` | `development` | Local dev with hot-reload | Volume mounts, DEBUG logging, relaxed rate limits |
| `test` | `production` image + test env vars | Integration + E2E testing | Separate DB (port 5433), short timeout (10s), max 5 articles |
| `production` | `production` | Live deployment | Non-root user, no source mount, uvloop + httptools |

---

## 8. Release Process

### Versioning Strategy

StockLens AI uses **Semantic Versioning** (`MAJOR.MINOR.PATCH`) for releases, managed via Git tags.

| Version segment | Trigger |
|---|---|
| `PATCH` (`1.0.X`) | Bug fixes, non-breaking changes to existing functionality |
| `MINOR` (`1.X.0`) | New features (new API endpoint, new pipeline step, new data source) |
| `MAJOR` (`X.0.0`) | Breaking API contract changes (removed endpoint, changed response shape) |

**Release tagging:**

```bash
git tag -a v1.0.0 -m "Phase 1 MVP release"
git push origin v1.0.0
```

The `docker/metadata-action` in the CI pipeline automatically tags Docker images with the semver tag when a Git tag is pushed:

```
ghcr.io/owner/stocklens-api:v1.0.0
ghcr.io/owner/stocklens-api:1.0
ghcr.io/owner/stocklens-api:latest
```

### Release Checklist

```markdown
## Release Checklist — v{VERSION}

### Pre-Release
- [ ] All CI checks green on `main`
- [ ] `CHANGELOG.md` updated with release notes
- [ ] Database migration tested on a copy of production data (partial restore to staging)
- [ ] `alembic upgrade head` verified on staging environment
- [ ] Non-financial-advice disclaimer text reviewed (if changed)
- [ ] API response contract verified against API documentation page
- [ ] Environment variables for new features added to `.env.example`
- [ ] Load test run against staging environment

### Deployment
- [ ] Git tag pushed: `git tag -a vX.Y.Z && git push origin vX.Y.Z`
- [ ] GitHub Actions `deploy-production` workflow approved (manual gate)
- [ ] Migration applied on production: verified via `SELECT version_num FROM alembic_version`
- [ ] `/health` endpoints return 200 post-deploy

### Post-Release
- [ ] Grafana: P50/P95 pipeline duration normal (within 20% of pre-deploy baseline)
- [ ] Error rate < 1% in first 30 minutes
- [ ] No `ERROR` or `CRITICAL` log events in Loki in first 30 minutes
- [ ] GitHub release created with changelog entries
```

---

## 9. Database Migration Rollout

### Safe Migration Deployment Sequence

Migrations are applied as part of the deployment, not as a separate manual step. The deployment script runs:

```bash
docker compose run --rm api alembic upgrade head
```

This runs before `docker compose up -d api frontend` — ensuring the schema is updated before new application code starts handling requests.

### Migration Strategy per Change Type

**Additive changes (new table, new nullable column, new index):**

```
deploy → migration runs → new app code starts
```

Safe in all cases. Old app code ignores new columns. New app code reads new columns.

**Column rename / type change:**

```
Step 1: Add new column (nullable), deploy
Step 2: Backfill new column from old column, verify
Step 3: Update application to write both old and new
Step 4: Update application to read from new column only
Step 5: Drop old column, deploy
```

This multi-step approach eliminates any window where the schema is incompatible with the running code.

**Column removal:**
Same as column rename — always a two-deploy minimum.

**Breaking changes to `report_data` JSONB schema:**
The `report_data` column stores versioned JSON. The `schema_version` field in the JSON allows the application to handle multiple schema versions:

```python
def parse_report_data(raw: dict) -> AnalysisReport:
    schema_version = raw.get("schema_version", "1")
    if schema_version == "1":
        return AnalysisReportV1.model_validate(raw).to_current()
    if schema_version == "2":
        return AnalysisReportV2.model_validate(raw).to_current()
    return AnalysisReport.model_validate(raw)
```

Old reports in the database remain readable after schema evolution. New reports are written with the current schema version.

### Rollback Path for Failed Migrations

If `alembic upgrade head` fails mid-migration:

```bash
# Roll back to the previous revision
alembic downgrade -1

# Verify
alembic current

# Restart old application containers (still running old image from previous deploy)
docker compose up -d --no-deps api frontend
```

Because the deployment script runs migrations before replacing containers, the old containers are still running during migration. If migration fails, the old containers continue serving traffic uninterrupted — the deployment fails safely without causing downtime.

---

## 10. Rollback Strategy

### Application Rollback

To roll back to the previous release:

```bash
# On the production server
cd /opt/stocklens

# Replace image tags in the .env or override file
export API_IMAGE=ghcr.io/owner/stocklens-api:v1.0.0   # previous version tag
export FRONTEND_IMAGE=ghcr.io/owner/stocklens-frontend:v1.0.0

docker compose -f infra/docker-compose.prod.yml pull
docker compose -f infra/docker-compose.prod.yml up -d --no-deps api frontend

# Verify
curl -sf http://localhost:8000/health
```

**Rollback duration:** Approximately 2–3 minutes (pull + start new containers + health check).

### Database Rollback

If the migration introduced a breaking schema change and the application rollback alone is insufficient:

```bash
# Roll back schema one revision
alembic downgrade -1

# Verify application is compatible with the rolled-back schema
curl -sf http://localhost:8000/health
```

**When downgrade is NOT possible:** If the migration created a new table with data written to it by the new application code, downgrading drops that table and the data. The downgrade script for such migrations must handle data migration back to the old schema or explicitly document that the downgrade is destructive. This constraint is enforced by the migration compatibility rules in `08_BACKUP_AND_RECOVERY.md`.

### Last-Resort Rollback: Restore from Backup

If both application and schema rollback fail:

```bash
# Follow 08_BACKUP_AND_RECOVERY.md full restore procedure
./scripts/restore.sh /backups/daily/2025-03-10/stocklens_db_...enc "$DATABASE_URL"
```

This returns the system to the state at the previous night's backup, with an RPO of up to 24 hours.

---

## 11. Monitoring and Alerting Setup

### Prometheus Configuration

```yaml
# infra/monitoring/prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'stocklens-api'
    static_configs:
      - targets: ['api:8000']
    metrics_path: '/metrics'

  - job_name: 'redis'
    static_configs:
      - targets: ['redis-exporter:9121']   # redis_exporter sidecar

  - job_name: 'postgres'
    static_configs:
      - targets: ['postgres-exporter:9187'] # pg_exporter sidecar

  - job_name: 'node'
    static_configs:
      - targets: ['node-exporter:9100']     # host metrics
```

### Grafana Alert Rules

```yaml
# Configured in Grafana UI / provisioning

alert: PipelineHighErrorRate
expr: |
  rate(pipeline_runs_total{status=~"failed|timed_out"}[5m])
  /
  rate(pipeline_runs_total[5m]) > 0.05
for: 5m
labels:
  severity: warning
annotations:
  summary: "Pipeline error rate > 5% for 5 minutes"

alert: PipelineP95LatencyHigh
expr: |
  histogram_quantile(0.95,
    rate(pipeline_duration_seconds_bucket[5m])
  ) > 75
for: 10m
labels:
  severity: warning
annotations:
  summary: "P95 pipeline duration > 75s for 10 minutes"

alert: OllamaUnreachable
expr: |
  rate(external_provider_errors_total{provider="ollama"}[5m]) > 0.5
for: 2m
labels:
  severity: critical
annotations:
  summary: "Ollama LLM provider returning errors"

alert: DatabaseConnectionPoolExhausted
expr: |
  pg_stat_database_numbackends{datname="stocklens"} > 18
for: 1m
labels:
  severity: critical
annotations:
  summary: "PostgreSQL connection pool near exhaustion (>18/20 connections)"

alert: HighRateLimitRejectionRate
expr: |
  rate(rate_limit_rejections_total[5m]) > 1
for: 5m
labels:
  severity: info
annotations:
  summary: "Elevated rate limit rejections — possible abuse or high traffic"

alert: BackupMissed
expr: |
  time() - stocklens_last_backup_timestamp_seconds > 90000
for: 0m
labels:
  severity: critical
annotations:
  summary: "No successful backup in the last 25 hours"
```

### Health Check Endpoints

```python
# app/api/routers/health.py

@router.get("/health")
async def health_check(
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    redis: Redis = Depends(get_redis)
):
    """
    Returns 200 if all critical dependencies are reachable.
    Returns 503 if any critical dependency is down.
    Used by Docker healthcheck, Nginx upstream health, and deployment scripts.
    """
    checks = {}

    # Database
    try:
        async with db_pool.acquire(timeout=2) as conn:
            await conn.fetchval("SELECT 1")
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {str(e)[:50]}"

    # Redis
    try:
        await redis.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {str(e)[:50]}"

    # Ollama (non-blocking — Ollama outage is not a system failure)
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            r = await client.get(f"{settings.ollama_url}/api/tags")
            checks["ollama"] = "ok" if r.status_code == 200 else f"status:{r.status_code}"
    except Exception:
        checks["ollama"] = "unreachable"

    is_healthy = checks["database"] == "ok" and checks["redis"] == "ok"

    return JSONResponse(
        status_code=200 if is_healthy else 503,
        content={
            "status": "healthy" if is_healthy else "degraded",
            "checks": checks,
            "version": settings.app_version
        }
    )
```

---

## 12. Storage Footprint Control Strategy

| Resource | Limit | Enforcement |
|---|---|---|
| PostgreSQL `analysis_runs` table | ~500MB max (estimated) | 24h TTL hard delete by cleanup job |
| PostgreSQL `pipeline_steps` table | ~2GB max | Cascade-deleted with parent run |
| Redis keyspace | 128MB hard limit | `maxmemory 128mb` + `allkeys-lru` eviction |
| Docker log files (per container) | 10MB per file, 3 files | `max-size: 10m, max-file: 3` in compose |
| Loki log retention | 30 days | `retention_period: 720h` in Loki config |
| Local backup volume | 7 daily + 4 weekly + 3 monthly ≈ ~500MB | Retention cleanup cron job |
| Prometheus TSDB | 15 days (default) | `--storage.tsdb.retention.time=15d` |
| Ollama model volume | ~4.5GB (`mistral:7b-instruct`) | Fixed; only grows if additional models are pulled |
