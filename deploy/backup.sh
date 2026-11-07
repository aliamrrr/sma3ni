#!/usr/bin/env bash
# Nightly PostgreSQL dump, 14 days kept locally. Cron (as the app user):
#   15 3 * * * cd ~/sma3ni && ./deploy/backup.sh >> backups/backup.log 2>&1
# Copy dumps off the server (recommended): a dedicated S3 bucket or any remote storage.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups && chmod 700 backups

file="backups/sma3ni-$(date +%Y%m%d-%H%M%S).sql.gz"
docker compose exec -T postgres pg_dump -U sma3ni -d sma3ni --format=plain --no-owner | gzip -9 >"$file"
chmod 600 "$file"
find backups -name 'sma3ni-*.sql.gz' -mtime +14 -delete
echo "$(date -Is) backup ok: $file ($(du -h "$file" | cut -f1))"

# aws s3 cp "$file" "s3://<backup-bucket>/postgres/" --sse aws:kms
