#!/usr/bin/env bash
# scripts/deploy.sh
# Server-side deployment script — called by GitHub Actions via SSH action.
#
# Performs a rolling deployment of the API and frontend containers:
#   1. Authenticate to GHCR
#   2. Pull latest images
#   3. Run Alembic migrations (before replacing containers)
#   4. Replace API and frontend containers (keep db/redis/ollama running)
#   5. Health check gate
#
# Required env vars (injected by CI or set in /opt/stocklens/.env.prod):
#   GHCR_TOKEN    — GitHub Personal Access Token with read:packages scope
#   GITHUB_ACTOR  — GitHub username for GHCR login
#   REPO_OWNER    — GitHub repository owner (for image references)
#
# Optional env vars:
#   COMPOSE_FILE  — path to production compose file (default: infra/docker-compose.prod.yml)
#   HEALTH_RETRIES — number of health check retries (default: 6)
#   HEALTH_WAIT    — seconds between health check retries (default: 10)

set -euo pipefail

DEPLOY_DIR="${DEPLOY_DIR:-/opt/stocklens}"
COMPOSE_FILE="${COMPOSE_FILE:-${DEPLOY_DIR}/infra/docker-compose.prod.yml}"
HEALTH_RETRIES="${HEALTH_RETRIES:-6}"
HEALTH_WAIT="${HEALTH_WAIT:-10}"

cd "$DEPLOY_DIR"

echo "[deploy] Starting deployment at $(date -u)"
echo "[deploy] Compose file: $COMPOSE_FILE"

# ── Step 1: Authenticate to GHCR ─────────────────────────────────────────────
if [ -n "${GHCR_TOKEN:-}" ]; then
  echo "[deploy] Step 1: Logging in to GHCR..."
  echo "$GHCR_TOKEN" | docker login ghcr.io -u "${GITHUB_ACTOR:-github}" --password-stdin
  echo "[deploy] GHCR login successful."
else
  echo "[deploy] Step 1: GHCR_TOKEN not set — skipping docker login (assuming already authenticated)."
fi

# ── Step 2: Pull latest images ────────────────────────────────────────────────
echo "[deploy] Step 2: Pulling latest API and frontend images..."
docker compose -f "$COMPOSE_FILE" pull api frontend
echo "[deploy] Images pulled."

# ── Step 3: Run Alembic migrations ───────────────────────────────────────────
# Migrations run BEFORE replacing containers so that if migration fails,
# the currently running containers (on the old schema) continue serving traffic.
echo "[deploy] Step 3: Running database migrations..."
docker compose -f "$COMPOSE_FILE" run --rm api alembic upgrade head
echo "[deploy] Migrations applied."

# ── Step 4: Rolling replacement of API and frontend ──────────────────────────
# --no-deps: keep db, redis, ollama, backup running — only replace api + frontend
echo "[deploy] Step 4: Replacing API and frontend containers..."
docker compose -f "$COMPOSE_FILE" up -d --no-deps api frontend
echo "[deploy] Containers replaced."

# ── Step 5: Health check gate ─────────────────────────────────────────────────
echo "[deploy] Step 5: Running health checks..."

api_healthy=false
for i in $(seq 1 "$HEALTH_RETRIES"); do
  echo "[deploy] Health check attempt ${i}/${HEALTH_RETRIES}..."
  sleep "$HEALTH_WAIT"

  if curl -sf --max-time 5 http://localhost:8000/health > /dev/null 2>&1; then
    echo "[deploy] API health check: PASSED"
    api_healthy=true
    break
  else
    echo "[deploy] API health check: not ready yet"
  fi
done

if [ "$api_healthy" = false ]; then
  echo "[deploy] ERROR: API failed to become healthy after ${HEALTH_RETRIES} attempts." >&2
  echo "[deploy] Showing recent API logs:" >&2
  docker compose -f "$COMPOSE_FILE" logs --tail=50 api >&2
  exit 1
fi

# Frontend health check (non-fatal — Next.js may take longer to start)
if curl -sf --max-time 5 http://localhost:3000/api/health > /dev/null 2>&1; then
  echo "[deploy] Frontend health check: PASSED"
else
  echo "[deploy] WARNING: Frontend health check did not pass — may still be starting."
fi

echo ""
echo "[deploy] ================================================================"
echo "[deploy] Deployment successful: $(date -u)"
echo "[deploy] ================================================================"
