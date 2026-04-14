#!/usr/bin/env bash
# scripts/verify_backup.sh
# Three-pass integrity verification for an encrypted backup file.
#
# Usage:
#   verify_backup.sh <path-to-.sql.gz.enc> <path-to-.manifest.json>
#
# Required env vars:
#   BACKUP_ENCRYPTION_KEY — AES-256-CBC passphrase matching the backup's key_identifier

set -euo pipefail

: "${BACKUP_ENCRYPTION_KEY:?BACKUP_ENCRYPTION_KEY is required}"

if [ $# -ne 2 ]; then
  echo "Usage: $0 <backup.sql.gz.enc> <manifest.json>" >&2
  exit 1
fi

BACKUP_FILE="$1"
MANIFEST_FILE="$2"

if [ ! -f "$BACKUP_FILE" ]; then
  echo "[verify] ERROR: Backup file not found: $BACKUP_FILE" >&2
  exit 1
fi

if [ ! -f "$MANIFEST_FILE" ]; then
  echo "[verify] ERROR: Manifest file not found: $MANIFEST_FILE" >&2
  exit 1
fi

echo "[verify] Starting integrity check for: $BACKUP_FILE"

# ── Pass 1: Verify post-encryption checksum ──────────────────────────────────
ACTUAL_SHA=$(sha256sum "$BACKUP_FILE" | cut -d' ' -f1)
EXPECTED_SHA=$(jq -r '.integrity.post_encryption_sha256' "$MANIFEST_FILE")

if [ "$ACTUAL_SHA" != "$EXPECTED_SHA" ]; then
  echo "[verify] FAILED: Post-encryption checksum mismatch. File may be corrupted." >&2
  echo "[verify] Expected: $EXPECTED_SHA" >&2
  echo "[verify] Actual:   $ACTUAL_SHA" >&2
  exit 1
fi
echo "[verify] Pass 1 — Post-encryption checksum: OK"

# ── Pass 2: Decryption smoke test (first 1 KB) ───────────────────────────────
# Read only the first 1KB after decryption to confirm the key is correct
# without writing the full decrypted payload to disk.
if ! openssl enc -d -aes-256-cbc \
  -in "$BACKUP_FILE" \
  -pass env:BACKUP_ENCRYPTION_KEY \
  -pbkdf2 -iter 100000 -md sha256 2>/dev/null | \
  gzip -d 2>/dev/null | \
  head -c 1024 > /dev/null 2>&1; then
  echo "[verify] FAILED: Decryption smoke test failed. Key may be incorrect." >&2
  exit 1
fi
echo "[verify] Pass 2 — Decryption smoke test (1 KB): OK"

# ── Pass 3: Full decrypt + pre-encryption hash verification ─────────────────
TEMP_FILE=$(mktemp /tmp/stocklens_verify_XXXXXX.sql)
trap 'rm -f "$TEMP_FILE"' EXIT

openssl enc -d -aes-256-cbc \
  -in "$BACKUP_FILE" \
  -pass env:BACKUP_ENCRYPTION_KEY \
  -pbkdf2 -iter 100000 -md sha256 | \
  gzip -d > "$TEMP_FILE"

ACTUAL_PRE_SHA=$(sha256sum "$TEMP_FILE" | cut -d' ' -f1)
EXPECTED_PRE_SHA=$(jq -r '.integrity.pre_encryption_sha256' "$MANIFEST_FILE")

if [ "$ACTUAL_PRE_SHA" != "$EXPECTED_PRE_SHA" ]; then
  echo "[verify] FAILED: Pre-encryption hash mismatch. Backup content may be corrupted." >&2
  echo "[verify] Expected: $EXPECTED_PRE_SHA" >&2
  echo "[verify] Actual:   $ACTUAL_PRE_SHA" >&2
  exit 1
fi
echo "[verify] Pass 3 — Pre-encryption hash (full decrypt): OK"

# ── Update manifest with verification timestamp ──────────────────────────────
VERIFIED_AT=$(date -u +"%Y-%m-%dT%H%M%SZ")
jq --arg ts "$VERIFIED_AT" \
  '.integrity.verified_at = $ts' \
  "$MANIFEST_FILE" > "${MANIFEST_FILE}.tmp" && mv "${MANIFEST_FILE}.tmp" "$MANIFEST_FILE"

echo "[verify] Integrity check PASSED: $BACKUP_FILE"
echo "[verify] verified_at: $VERIFIED_AT"
