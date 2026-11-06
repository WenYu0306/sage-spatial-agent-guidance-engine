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
  out=${out// /}  # JSONResponse 紧凑输出 {"ok":true}，宽松匹配需去空格
  # grep -F 固定串匹配：[[ ]] 引号段+glob 混合模式在 macOS bash 3.2 有尾部 * 被转义的 bug
  echo "$out" | grep -qF '"ok":true' || { echo "  ✗ $name 未就绪"; fail=1; }
done
probe=${SAGE_HTTP:-127.0.0.1:8080}  # 与 compose SAGE_HTTP 绑定地址一致
# 3 次重试（间隔 3s）：deploy 重建容器后端口绑定可能晚于 --wait 的 Healthy 判定
code=000
for _ in 1 2 3; do
  code=$(curl -s -o /dev/null -w "%{http_code}" -m 5 "http://$probe/admin/" || true)
  [ "$code" == 200 ] || [ "$code" == 302 ] && break
  sleep 3
done
echo "  nginx(/admin/) → HTTP $code"
[[ "$code" == 200 || "$code" == 302 ]] || fail=1
exit $fail
