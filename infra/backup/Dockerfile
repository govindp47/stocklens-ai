FROM debian:bookworm-slim

# Avoid interactive prompts during package install
ENV DEBIAN_FRONTEND=noninteractive

# Install required tools:
#   postgresql-client — pg_dump, psql
#   openssl           — AES-256-CBC encryption/decryption
#   awscli            — S3 sync
#   python3 + asyncpg — validate_restore.py
#   jq                — manifest JSON manipulation
#   cron              — scheduled backup and verification jobs
#   curl              — health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    openssl \
    python3 \
    python3-pip \
    jq \
    cron \
    curl \
    ca-certificates \
    uuid-runtime \
    && pip3 install --no-cache-dir asyncpg awscli \
    && rm -rf /var/lib/apt/lists/*

# Copy backup scripts
COPY scripts/ /scripts/
RUN chmod +x /scripts/backup.sh /scripts/verify_backup.sh /scripts/restore.sh \
    && chmod +x /scripts/validate_restore.py

# Cron schedule — matches 08_BACKUP_AND_RECOVERY.md Section 11
RUN printf 'SHELL=/bin/bash\n\
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin\n\
\n\
# Daily full backup at 02:00 UTC\n\
0 2 * * * root /scripts/backup.sh >> /var/log/backup.log 2>&1\n\
\n\
# Daily integrity verification at 03:00 UTC (most recent backup)\n\
0 3 * * * root bash -c '\''LATEST_ENC=$(find /backups/daily -name "*.sql.gz.enc" | sort | tail -1); \
LATEST_MAN="${LATEST_ENC%.sql.gz.enc}.manifest.json"; \
[ -n "$LATEST_ENC" ] && /scripts/verify_backup.sh "$LATEST_ENC" "$LATEST_MAN"'\'' >> /var/log/backup-verify.log 2>&1\n\
' > /etc/cron.d/stocklens-backup \
    && chmod 0644 /etc/cron.d/stocklens-backup

# Create log files and backup mount point
RUN mkdir -p /backups/daily /backups/weekly /backups/monthly /var/log \
    && touch /var/log/backup.log /var/log/backup-verify.log

# Prometheus textfile directory (optional — mount node-exporter textfile collector here)
RUN mkdir -p /var/lib/node_exporter/textfile_collector
ENV PROMETHEUS_TEXTFILE_DIR=/var/lib/node_exporter/textfile_collector

VOLUME ["/backups"]

# Start cron daemon in foreground
CMD ["cron", "-f"]
