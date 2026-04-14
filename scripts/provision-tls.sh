#!/usr/bin/env bash
# scripts/provision-tls.sh
# Provisions a Let's Encrypt TLS certificate for StockLens using Certbot
# (standalone mode — Nginx must NOT be running on port 80 during provisioning).
#
# Usage:
#   sudo ./scripts/provision-tls.sh <domain> [email]
#
# Example:
#   sudo ./scripts/provision-tls.sh stocklens.example.com ops@example.com
#
# For testing (uses Let's Encrypt staging endpoint — no rate limits):
#   CERTBOT_STAGING=1 sudo ./scripts/provision-tls.sh stocklens.example.com ops@example.com
#
# After provisioning, certificates are at:
#   /etc/letsencrypt/live/<domain>/fullchain.pem
#   /etc/letsencrypt/live/<domain>/privkey.pem
#
# These paths are referenced by infra/nginx/nginx-prod.conf and mounted into
# the Nginx container via docker-compose.prod.yml.

set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <domain> [email]" >&2
  exit 1
fi

DOMAIN="$1"
EMAIL="${2:-webmaster@${DOMAIN}}"
STAGING="${CERTBOT_STAGING:-0}"

echo "[tls] Provisioning TLS certificate for: $DOMAIN"
echo "[tls] Contact email: $EMAIL"

# ── Install Certbot ───────────────────────────────────────────────────────────
if ! command -v certbot > /dev/null 2>&1; then
  echo "[tls] Installing Certbot..."
  if command -v apt-get > /dev/null 2>&1; then
    apt-get update -q
    apt-get install -y --no-install-recommends certbot
  elif command -v yum > /dev/null 2>&1; then
    yum install -y certbot
  elif command -v dnf > /dev/null 2>&1; then
    dnf install -y certbot
  else
    echo "[tls] ERROR: Cannot install certbot — unsupported package manager." >&2
    echo "[tls] Install certbot manually: https://certbot.eff.org/" >&2
    exit 1
  fi
  echo "[tls] Certbot installed."
else
  echo "[tls] Certbot already installed: $(certbot --version 2>&1)"
fi

# ── Stop Nginx if running (standalone mode needs port 80) ─────────────────────
NGINX_WAS_RUNNING=false
if docker ps --format '{{.Names}}' 2>/dev/null | grep -q nginx; then
  echo "[tls] Stopping Nginx container for standalone certificate provisioning..."
  docker compose -f /opt/stocklens/infra/docker-compose.prod.yml stop nginx 2>/dev/null || true
  NGINX_WAS_RUNNING=true
fi

# ── Build certbot command ──────────────────────────────────────────────────────
CERTBOT_ARGS=(
  certonly
  --standalone
  --non-interactive
  --agree-tos
  --email "$EMAIL"
  --domain "$DOMAIN"
  --rsa-key-size 4096
)

if [ "$STAGING" = "1" ]; then
  CERTBOT_ARGS+=(--staging)
  echo "[tls] Using Let's Encrypt STAGING endpoint (test run — certificate NOT trusted by browsers)"
fi

# ── Run Certbot ────────────────────────────────────────────────────────────────
echo "[tls] Running certbot..."
certbot "${CERTBOT_ARGS[@]}"

echo "[tls] Certificate provisioned:"
ls -la "/etc/letsencrypt/live/${DOMAIN}/"

# ── Set up automatic renewal cron job ─────────────────────────────────────────
CRON_CMD="0 3 * * * root certbot renew --quiet --deploy-hook 'docker compose -f /opt/stocklens/infra/docker-compose.prod.yml exec nginx nginx -s reload'"
CRON_FILE="/etc/cron.d/certbot-stocklens"

if [ ! -f "$CRON_FILE" ]; then
  echo "[tls] Installing certificate renewal cron job at ${CRON_FILE}..."
  cat > "$CRON_FILE" <<EOF
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin

# Let's Encrypt certificate renewal — daily at 03:00 UTC
# Reloads Nginx after successful renewal
${CRON_CMD}
EOF
  chmod 0644 "$CRON_FILE"
  echo "[tls] Renewal cron job installed."
else
  echo "[tls] Renewal cron job already exists at ${CRON_FILE}."
fi

# ── Restart Nginx if it was running ───────────────────────────────────────────
if [ "$NGINX_WAS_RUNNING" = true ]; then
  echo "[tls] Restarting Nginx container..."
  docker compose -f /opt/stocklens/infra/docker-compose.prod.yml start nginx 2>/dev/null || true
fi

echo ""
echo "[tls] ================================================================"
echo "[tls] TLS certificate provisioning complete."
echo "[tls] Domain:  ${DOMAIN}"
if [ "$STAGING" = "1" ]; then
  echo "[tls] NOTE: This is a STAGING certificate. Run without CERTBOT_STAGING=1"
  echo "[tls]       to provision a trusted production certificate."
fi
echo "[tls] Renewal: ${CRON_FILE} (daily at 03:00 UTC)"
echo "[tls] ================================================================"
