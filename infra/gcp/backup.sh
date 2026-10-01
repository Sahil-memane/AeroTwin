#!/usr/bin/env bash
# Logical DB backup to /opt/aerotwin-backups (cron it daily; copy off-host with `gsutil cp` to a bucket).
#   0 2 * * * /opt/aerotwin/infra/gcp/backup.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
C="infra/docker"; OUT=/opt/aerotwin-backups; mkdir -p "$OUT"
F="$OUT/aerotwin-$(date +%F).dump"
docker compose --env-file "$C/.env.prod" -f "$C/docker-compose.prod.yml" exec -T db \
  sh -c 'pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB"' > "$F"
find "$OUT" -name '*.dump' -mtime +14 -delete
echo "wrote $F"
