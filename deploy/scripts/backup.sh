#!/usr/bin/env bash
# pg_dump 备份，保留 14 天（PRD 7.5 第 6 条）。建议 crontab：0 3 * * * bash deploy/scripts/backup.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p deploy/backups
f="deploy/backups/sage-$(date +%Y%m%d-%H%M%S).sql.gz"
docker compose -f deploy/compose.demo.yml exec -T postgres \
  pg_dump -U "${POSTGRES_USER:-sage}" "${POSTGRES_DB:-sage}" | gzip > "$f"
echo "备份完成：$f ($(du -h "$f" | cut -f1))"
find deploy/backups -name 'sage-*.sql.gz' -mtime +14 -delete
echo "已清理 14 天前备份"
