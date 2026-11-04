#!/usr/bin/env bash
# 回滚到上一版镜像 tag（deploy 时 SAGE_TAG 落在 deploy/.previous_release）。
set -euo pipefail
cd "$(dirname "$0")/../.."
prev=$(cat deploy/.previous_release 2>/dev/null || true)
[ -n "$prev" ] || { echo "无上一版记录（首次部署无回滚点）"; exit 1; }
echo "回滚到 tag：$prev"
SAGE_TAG="$prev" docker compose -f deploy/compose.demo.yml up -d
bash deploy/scripts/healthcheck.sh && echo "回滚完成" || echo "回滚后健康检查未通过，请人工介入"
