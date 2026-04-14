#!/usr/bin/env bash
# scripts/restore.sh
# Full disaster recovery restore from an encrypted backup.
#
# Usage:
#   restore.sh <path-to-.sql.gz.enc> <target-db-url>
#
# Required env vars:
#   BACKUP_ENCRYPTION_KEY — AES-256-CBC passphrase matching the backup's key_identifier
#
# The script:
#   1. Verifies backup integrity (calls verify_backup.sh)
#   2. Decrypts and decompresses to a temp file
#   3. Prompts for CONFIRM before destroying the target database
#   4. Drops and recreates the database
#   5. Restores the SQL dump
#   6. Runs alembic upgrade head
#   7. Runs validate_restore.py assertions

set -euo pipefail

: "${BACKUP_ENCRYPTION_KEY:?BACKUP_ENCRYPTION_KEY is required}"

if [ $# -ne 2 ]; then
  echo "Usage: $0 <backup.sql.gz.enc> <target-db-url>" >&2
  exit 1
fi

BACKUP_FILE="$1"
TARGET_DB_URL="$2"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST_FILE="${BACKUP_FILE%.sql.gz.enc}.manifest.json"

if [ ! -f "$BACKUP_FILE" ]; then
  echo "[restore] ERROR: Backup file not found: $BACKUP_FILE" >&2
  exit 1
fi

if [ ! -f "$MANIFEST_FILE" ]; then
  echo "[restore] ERROR: Manifest file not found: $MANIFEST_FILE" >&2
  exit 1
fi

# ── Step 1: Verify integrity before restore ───────────────────────────────────
echo "[restore] Step 1: Verifying backup integrity..."
"${SCRIPT_DIR}/verify_backup.sh" "$BACKUP_FILE" "$MANIFEST_FILE"
echo "[restore] Integrity verification passed."

# ── Step 2: Decrypt and decompress to temp file ───────────────────────────────
TEMP_SQL=$(mktemp /tmp/stocklens_restore_XXXXXX.sql)
trap 'rm -f "$TEMP_SQL"; echo "[restore] Cleaned up temp file."' EXIT

echo "[restore] Step 2: Decrypting and decompressing backup..."
openssl enc -d -aes-256-cbc \
  -in "$BACKUP_FILE" \
  -pass env:BACKUP_ENCRYPTION_KEY \
  -pbkdf2 -iter 100000 -md sha256 | \
  gzip -d > "$TEMP_SQL"

echo "[restore] Decrypted dump size: $(du -sh "$TEMP_SQL" | cut -f1)"

# ── Step 3: Confirmation prompt ───────────────────────────────────────────────
echo ""
echo "[restore] WARNING: This will DESTROY all existing data in the target database."
echo "[restore] Target: ${TARGET_DB_URL}"
echo "[restore] Backup: $(basename "$BACKUP_FILE")"
echo "[restore] Backup created at: $(jq -r '.created_at' "$MANIFEST_FILE")"
echo ""
read -r -p "Type 'CONFIRM' to proceed: " confirmation
if [ "$confirmation" != "CONFIRM" ]; then
  echo "[restore] Aborted by user."
  exit 1
fi

# ── Step 4: Drop and recreate the database ────────────────────────────────────
# Extract base URL (strip database name) for connecting to postgres admin db
# e.g. postgresql://user:pass@host:5432/stocklens -> postgresql://user:pass@host:5432/postgres
DB_NAME=$(echo "$TARGET_DB_URL" | sed 's|.*/||' | sed 's|?.*||')
ADMIN_URL=$(echo "$TARGET_DB_URL" | sed "s|/${DB_NAME}$|/postgres|" | sed "s|/${DB_NAME}?|/postgres?|")

echo "[restore] Step 4: Dropping and recreating database '${DB_NAME}'..."
psql "$ADMIN_URL" -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${DB_NAME}' AND pid <> pg_backend_pid();" > /dev/null 2>&1 || true
psql "$ADMIN_URL" -c "DROP DATABASE IF EXISTS \"${DB_NAME}\";"
psql "$ADMIN_URL" -c "CREATE DATABASE \"${DB_NAME}\";"
echo "[restore] Database recreated."

# ── Step 5: Restore SQL dump ──────────────────────────────────────────────────
echo "[restore] Step 5: Restoring database from dump..."
psql "$TARGET_DB_URL" < "$TEMP_SQL"
echo "[restore] Database restore complete."

# ── Step 6: Run Alembic forward migrations ────────────────────────────────────
BACKUP_SCHEMA=$(jq -r '.database.schema_version' "$MANIFEST_FILE")
echo "[restore] Step 6: Backup schema version: ${BACKUP_SCHEMA}"
echo "[restore] Running Alembic migrations to current head..."

APP_DIR="${APP_DIR:-/app}"
if [ -d "$APP_DIR" ] && command -v alembic > /dev/null 2>&1; then
  cd "$APP_DIR"
  DATABASE_URL="$TARGET_DB_URL" alembic upgrade head
  echo "[restore] Alembic migrations applied."
else
  echo "[restore] WARNING: alembic not found or /app not mounted — skipping migrations."
  echo "[restore] Run 'alembic upgrade head' manually before starting the application."
fi

# ── Step 7: Validate restored data ───────────────────────────────────────────
echo "[restore] Step 7: Running post-restore validation..."

VALIDATE_SCRIPT="${SCRIPT_DIR}/validate_restore.py"
if [ -f "$VALIDATE_SCRIPT" ]; then
  DATABASE_URL="$TARGET_DB_URL" python3 "$VALIDATE_SCRIPT" "$MANIFEST_FILE"
  echo "[restore] Validation passed."
else
  echo "[restore] WARNING: validate_restore.py not found — skipping validation."
  # Minimal manual validation
  psql "$TARGET_DB_URL" -c "SELECT COUNT(*) AS run_count FROM analysis_runs;"
  psql "$TARGET_DB_URL" -c "SELECT version_num FROM alembic_version;"
fi

echo ""
echo "[restore] ================================================================"
echo "[restore] Restore complete: $(date -u)"
echo "[restore] Restored from: $(basename "$BACKUP_FILE")"
echo "[restore] Target database: ${TARGET_DB_URL}"
echo "[restore] ================================================================"
