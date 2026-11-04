#!/usr/bin/env bash
# 各服务 /health + 公网可达性；任一失败退出非零（deploy.sh 与独立排查共用）。
set -uo pipefail
cd "$(dirname "$0")/../.."
fail=0
for svc in content:8945 route-engine:8942 knowledge-rag:8943 recommender:8944 analytics:8946 agent:8941; do
  name=${svc%%:*}; port=${svc##*:}
  out=$(docker compose -f deploy/compose.demo.yml exec -T "$name" \
    python -c "import urllib.request as u;print(u.urlopen('http://127.0.0.1:$port/health',timeout=3).read().decode())" 2>&1 | tail -1)
  echo "  $name(/health) → $out"
  [[ "$out" == *'"ok": true'* ]] || { echo "  ✗ $name 未就绪"; fail=1; }
done
code=$(curl -s -o /dev/null -w "%{http_code}" -m 5 http://127.0.0.1:8080/admin/ || true)
echo "  nginx(/admin/) → HTTP $code"
[[ "$code" == 200 || "$code" == 302 ]] || fail=1
exit $fail
