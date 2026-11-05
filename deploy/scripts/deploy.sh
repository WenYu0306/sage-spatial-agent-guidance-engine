#!/usr/bin/env bash
# M13 demo 部署：拉码 → 构建镜像 → 起基础设施 → 迁移(幂等) → 起服务 → 健康检查 → 灌数据 → 输出地址。
# 用法：在服务器仓库根执行  bash deploy/scripts/deploy.sh
# 说明（PRD 7.5 偏差，见 D-026）：无镜像仓库，"拉镜像"以"git pull + 本机构建"实现。
set -euo pipefail
cd "$(dirname "$0")/../.."
# 镜像 tag：git SHA 优先（rsync 快照模式退化为时间戳）；回滚点在起服务前落盘
export SAGE_TAG="${SAGE_TAG:-$(git rev-parse --short HEAD 2>/dev/null || echo "rsync-$(date +%H%M)")}"
if [ -d .git ]; then
  BRANCH=$(git rev-parse --abbrev-ref HEAD)
  SHA=$(git rev-parse --short HEAD)
  echo "== [1/7] 拉取代码（$BRANCH @ ${SHA}）=="
  # 服务器（腾讯云）与开发机到 github 均间歇抖动：有界重试而非一次定生死
  pull_ok=0
  for _ in 1 2 3; do
    if git pull --ff-only origin "$BRANCH"; then pull_ok=1; break; fi
    echo "  （pull 失败，15s 后重试）"
    sleep 15
  done
  [ "$pull_ok" = "1" ] || { echo "✗ 拉取代码连续失败，中止部署"; exit 1; }
else
  SHA="rsync-$(date +%H%M)"
  echo "== [1/7] 代码就绪（rsync 同步模式：无 .git，跳过 pull——D-026，快照 ${SHA}）=="
fi
echo "== [2/7] 构建镜像 =="
if [ "${SKIP_BUILD:-0}" = "1" ]; then
  echo "（SHIP 模式：镜像已由本机构建并载入，跳过构建——D-026）"
else
  docker compose -f deploy/compose.demo.yml build
fi
echo "== [3/7] 起基础设施（postgres/redis）=="
docker compose -f deploy/compose.demo.yml up -d --wait --wait-timeout 180 postgres redis
echo "== [4/7] 数据库迁移（幂等）=="
docker compose -f deploy/compose.demo.yml run --rm migrate
echo "== [5/7] 起全部服务 =="
# 回滚点：重建前记录当前运行镜像 tag（首次部署无记录，rollback.sh 会明确提示）
AGENT_CID=$(docker compose -f deploy/compose.demo.yml ps -q agent 2>/dev/null || true)
if [ -n "${AGENT_CID:-}" ]; then
  PREV_TAG=$(docker inspect --format '{{.Config.Image}}' "$AGENT_CID" | sed 's/^sage-backend://')
  if [ -n "$PREV_TAG" ]; then
    echo "$PREV_TAG" > deploy/.previous_release
    echo "（回滚点已记录：${PREV_TAG}）"
  fi
fi
# --wait：等全部服务达到 healthy（无 healthcheck 的等 running）再进体检，消除启动竞态
docker compose -f deploy/compose.demo.yml up -d --wait --wait-timeout 180
echo "== [6/7] 健康检查 =="
bash deploy/scripts/healthcheck.sh
echo "== [7/7] 灌 demo 数据（seed 幂等 + ingest 知识向量）=="
docker compose -f deploy/compose.demo.yml run --rm seed
docker compose -f deploy/compose.demo.yml run --rm ingest
echo "== 部署完成 =="
echo "公网地址：https://sage.westwardecho.com/admin/"
echo "本机直连：http://127.0.0.1:${SAGE_HTTP_PORT:-8080}/admin/（服务器上）"
docker compose -f deploy/compose.demo.yml ps
