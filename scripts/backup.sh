#!/usr/bin/env bash
# scripts/backup.sh
# Runs inside the backup container (has pg_dump available, mounts /backups volume)
#
# Required env vars:
#   DATABASE_URL            — postgresql://user:pass@host:5432/dbname
#   BACKUP_ENCRYPTION_KEY   — AES-256-CBC passphrase (PBKDF2)
# Optional env vars:
#   ENVIRONMENT             — production|staging (default: production)
#   BACKUP_KEY_ID           — identifier for the encryption key (default: backup-key-default)
#   BACKUP_S3_BUCKET        — S3 bucket name; if set, syncs backup to S3
#   PROMETHEUS_TEXTFILE_DIR — if set, writes last_backup_timestamp metric to this dir

set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL is required}"
: "${BACKUP_ENCRYPTION_KEY:?BACKUP_ENCRYPTION_KEY is required}"

TIMESTAMP=$(date -u +"%Y-%m-%dT%H%M%SZ")
SCHEMA_VERSION=$(psql "$DATABASE_URL" -t -c "SELECT version_num FROM alembic_version LIMIT 1" | tr -d ' \n')
ENV="${ENVIRONMENT:-production}"
BACKUP_DIR="/backups/daily/${TIMESTAMP:0:10}"
BASENAME="stocklens_db_${TIMESTAMP}_v${SCHEMA_VERSION}_${ENV}"

mkdir -p "$BACKUP_DIR"

echo "[backup] Starting PostgreSQL dump..."

# 1. Dump — plain SQL format (human-readable; compatible with pg_restore and psql)
pg_dump \
  --no-owner \
  --no-privileges \
  --clean \
  --if-exists \
  --format=plain \
  --dbname="$DATABASE_URL" \
  > "${BACKUP_DIR}/${BASENAME}.sql"

# 2. Compute pre-compression, pre-encryption hash
PRE_ENCRYPT_SHA=$(sha256sum "${BACKUP_DIR}/${BASENAME}.sql" | cut -d' ' -f1)
echo "[backup] Pre-encryption SHA256: ${PRE_ENCRYPT_SHA}"

# 3. Compress
gzip -9 "${BACKUP_DIR}/${BASENAME}.sql"

# 4. Encrypt
openssl enc -aes-256-cbc \
  -in  "${BACKUP_DIR}/${BASENAME}.sql.gz" \
  -out "${BACKUP_DIR}/${BASENAME}.sql.gz.enc" \
  -pass env:BACKUP_ENCRYPTION_KEY \
  -pbkdf2 -iter 100000 -md sha256

rm "${BACKUP_DIR}/${BASENAME}.sql.gz"   # remove unencrypted compressed file

# 5. Post-encryption checksum
POST_ENCRYPT_SHA=$(sha256sum "${BACKUP_DIR}/${BASENAME}.sql.gz.enc" | cut -d' ' -f1)
echo "${POST_ENCRYPT_SHA}  ${BASENAME}.sql.gz.enc" > "${BACKUP_DIR}/${BASENAME}.sql.gz.enc.sha256"

# 6. Collect row counts for manifest
ROW_COUNTS=$(psql "$DATABASE_URL" -t -A -c "
  SELECT json_build_object(
    'analysis_runs',          (SELECT COUNT(*) FROM analysis_runs),
    'pipeline_steps',         (SELECT COUNT(*) FROM pipeline_steps),
    'system_metrics_hourly',  (SELECT COUNT(*) FROM system_metrics_hourly),
    'ticker_resolution_cache',(SELECT COUNT(*) FROM ticker_resolution_cache),
    'rate_limit_log',         (SELECT COUNT(*) FROM rate_limit_log)
  )::text
")

# 7. Gather file metadata
ENCRYPTED_BYTES=$(stat -c%s "${BACKUP_DIR}/${BASENAME}.sql.gz.enc")
EXPIRES_AT=$(date -u -d "+7 days" +"%Y-%m-%dT%H%M%SZ" 2>/dev/null \
  || date -u -v+7d +"%Y-%m-%dT%H%M%SZ")   # macOS fallback

# Get PostgreSQL version from server
PG_VERSION=$(psql "$DATABASE_URL" -t -A -c "SHOW server_version" | tr -d ' ')

# Get alembic head revision
ALEMBIC_HEAD=$(psql "$DATABASE_URL" -t -A -c "SELECT version_num FROM alembic_version LIMIT 1" | tr -d ' ')

# Generate UUID (use python3 as portable fallback if uuidgen unavailable)
BACKUP_UUID=$(python3 -c "import uuid; print(uuid.uuid4())" 2>/dev/null || uuidgen)

# 8. Write manifest
cat > "${BACKUP_DIR}/${BASENAME}.manifest.json" <<EOF
{
  "backup_id": "${BACKUP_UUID}",
  "created_at": "${TIMESTAMP}",
  "environment": "${ENV}",
  "backup_type": "full",
  "database": {
    "host": "db",
    "port": 5432,
    "name": "stocklens",
    "pg_version": "${PG_VERSION}",
    "schema_version": "${SCHEMA_VERSION}",
    "alembic_head": "${ALEMBIC_HEAD}",
    "table_row_counts": ${ROW_COUNTS}
  },
  "files": {
    "dump_file": "${BASENAME}.sql.gz.enc",
    "dump_file_sha256": "${POST_ENCRYPT_SHA}",
    "dump_encrypted_bytes": ${ENCRYPTED_BYTES},
    "manifest_file": "${BASENAME}.manifest.json"
  },
  "encryption": {
    "algorithm": "AES-256-CBC",
    "key_identifier": "${BACKUP_KEY_ID:-backup-key-default}",
    "iv_embedded": true
  },
  "integrity": {
    "pre_encryption_sha256": "${PRE_ENCRYPT_SHA}",
    "post_encryption_sha256": "${POST_ENCRYPT_SHA}",
    "verified_at": null
  },
  "retention": {
    "expires_at": "${EXPIRES_AT}",
    "policy": "7d-daily-4w-weekly-3m-monthly"
  }
}
EOF

echo "[backup] Backup complete: ${BASENAME}"
echo "[backup] Files:"
echo "  ${BACKUP_DIR}/${BASENAME}.sql.gz.enc"
echo "  ${BACKUP_DIR}/${BASENAME}.sql.gz.enc.sha256"
echo "  ${BACKUP_DIR}/${BASENAME}.manifest.json"

# 9. Write Prometheus textfile metric (for BackupMissed alert)
if [ -n "${PROMETHEUS_TEXTFILE_DIR:-}" ]; then
  mkdir -p "$PROMETHEUS_TEXTFILE_DIR"
  EPOCH=$(date +%s)
  cat > "${PROMETHEUS_TEXTFILE_DIR}/backup.prom" <<PROM
# HELP stocklens_last_backup_timestamp_seconds Unix timestamp of the last successful backup
# TYPE stocklens_last_backup_timestamp_seconds gauge
stocklens_last_backup_timestamp_seconds ${EPOCH}
PROM
  echo "[backup] Wrote Prometheus metric: stocklens_last_backup_timestamp_seconds=${EPOCH}"
fi

# 10. Sync to remote storage (S3-compatible)
if [ -n "${BACKUP_S3_BUCKET:-}" ]; then
  aws s3 sync "${BACKUP_DIR}" "s3://${BACKUP_S3_BUCKET}/daily/${TIMESTAMP:0:10}/" \
    --storage-class STANDARD_IA \
    --sse AES256
  echo "[backup] Synced to S3: s3://${BACKUP_S3_BUCKET}/daily/${TIMESTAMP:0:10}/"
fi
