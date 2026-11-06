#!/usr/bin/env bash
# 13.5 故障演练（6 条降级路径验证）：每条 演练→断言→恢复。
# 用法：bash scripts/chaos_test.sh
# 前提：后端全起（8941-8946），docker compose 的 postgres/redis 在跑。
set -u
PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); echo "  ✓ $1"; }
fail() { FAIL=$((FAIL+1)); echo "  ✗ $1"; }
assert_contains() {
  if echo "$1" | grep -q "$2"; then ok "$3"; else fail "$3（缺 $2）"; fi
}
assert_not_contains() {
  # 审查 E14：grep -v 是逐行取反——多行输入只要有一行不匹配就 exit 0，
  # 断言恒真（体检仪失明）。改为整体 -q 匹配后取反结果。
  if echo "$1" | grep -q "$2"; then fail "$3（命中 $2）"; else ok "$3"; fi
}

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
set -a; source .env > /dev/null 2>&1; set +a

_get() { python3 -c "
import httpx, sys
try:
    r = httpx.get(sys.argv[1], timeout=10)
    print(r.text)
except Exception as e:
    print('CHAOS_ERROR')
" "$1"; }

_post_chat() { python3 -c "
import httpx, sys
try:
    r = httpx.post('http://127.0.0.1:' + sys.argv[2] + '/api/v1/agent/chat',
                   json={'venue_id': 1, 'message': sys.argv[1]}, timeout=30)
    print(r.text)
except Exception as e:
    print('CHAOS_ERROR')
" "$1" "${2:-8941}"; }

echo "====== 13.5 故障演练 ======"

# ---------- ① 模型 API Key 篡改 ----------
echo "--- ① 模型 API Key 篡改 → 3001 兜底"
set -a; source .env > /dev/null 2>&1; set +a
export LLM_API_KEY="sk-chaos-invalid-key-000"
uv run uvicorn agent_orchestrator.app:app --host 127.0.0.1 --port 8947 \
  > /tmp/chaos-agent.log 2>&1 &
CHAOS_PID=$!
sleep 4
BODY=$(_post_chat "我想吃火锅" 8947)
assert_contains "$BODY" "3001" "① 错误码 3001"
assert_contains "$BODY" "服务台" "① 兜底话术含服务台指引"
assert_not_contains "$BODY" "Traceback" "① 不泄漏堆栈"
kill $CHAOS_PID 2>/dev/null; wait $CHAOS_PID 2>/dev/null
echo "  （chaos agent 已停）"

# ---------- ② 停 Redis ----------
echo "--- ② 停 Redis → 服务不整体崩溃"
docker stop sage-redis > /dev/null 2>&1; sleep 2
H=$(python3 -c "import httpx; print(httpx.get('http://127.0.0.1:8941/health',timeout=5).text)")
assert_contains "$H" "ok" "② agent health 正常"
H2=$(python3 -c "import httpx; print(httpx.get('http://127.0.0.1:8945/health',timeout=5).text)")
assert_contains "$H2" "ok" "② content health 正常"
docker start sage-redis > /dev/null 2>&1; sleep 2
echo "  （Redis 已恢复）"

# ---------- ③ kill agent → 其余端正常 ----------
echo "--- ③ kill agent → 其余服务不受影响"
kill $(lsof -t -nP -iTCP:8941 -sTCP:LISTEN) 2>/dev/null; sleep 2
H5=$(python3 -c "import httpx; print(httpx.get('http://127.0.0.1:8945/health',timeout=5).text)")
assert_contains "$H5" "ok" "③ content 不受影响"
POIS=$(python3 -c "import httpx; r=httpx.get('http://127.0.0.1:8945/api/v1/pois',params={'venue_id':1,'status':'published','limit':3},timeout=5); print(r.text)")
assert_contains "$POIS" '"name"' "③ POI 查询正常"
set -a; source .env > /dev/null 2>&1; set +a
uv run uvicorn agent_orchestrator.app:app --host 127.0.0.1 --port 8941 \
  > /tmp/svc-agent.log 2>&1 &
sleep 4
H1=$(python3 -c "import httpx; print(httpx.get('http://127.0.0.1:8941/health',timeout=5).text)")
assert_contains "$H1" "ok" "③ agent 已恢复"

# ---------- ④ 路网越界节点不 500 ----------
echo "--- ④ 路网越界坐标 → 2004/2003（不 500）"
DIRTY_NODE=$(docker exec sage-postgres psql -U sage -d sage -t -A -q -c "
  insert into route_nodes (tenant_id, venue_id, floor_id, node_type, x, y, accessible)
  values (1, 1, 2, 'waypoint', -9999, 99999, true) returning id;" 2>/dev/null | tr -d '[:space:]')
VALID_NODE=$(docker exec sage-postgres psql -U sage -d sage -t -A -q -c "
  select id from route_nodes where venue_id=1 and node_type='waypoint' limit 1;" \
  2>/dev/null | tr -d '[:space:]')
BODY=$(python3 -c "
import httpx, os
try:
    r = httpx.post('http://127.0.0.1:8942/route/plan', json={
        'tenant_code': 'shanqueli-demo', 'venue_name': '山雀里·栖云广场',
        'start_node_id': int('$VALID_NODE'), 'goal_node_id': int('$DIRTY_NODE')},
        timeout=15)
    print(r.text)
except Exception as e:
    print('CHAOS_ERROR')
")
assert_contains "$BODY" "2003\|2004\|route" "④ 越界坐标不 500"
docker exec sage-postgres psql -U sage -d sage -c "
  delete from route_nodes where venue_id=1 and x=-9999 and y=99999;" > /dev/null 2>&1

# ---------- ⑤ SVG 注入安全 ----------
echo "--- ⑤ SVG 注入 → 静态资源不含可执行脚本"
for svg in "$REPO"/deploy/maps/*.svg; do
  SVG_CHECK=$(cat "$svg")
  SVG_NAME=$(basename "$svg")
  assert_not_contains "$SVG_CHECK" "<script" "⑤ $SVG_NAME 无 <script>"
  assert_not_contains "$SVG_CHECK" "javascript:" "⑤ $SVG_NAME 无 javascript: URI"
done

# ---------- ⑥ 大数据量分页 ----------
echo "--- ⑥ 大数据量列表 → 分页可用"
docker exec sage-postgres psql -U sage -d sage -c "
  insert into pois (tenant_id, venue_id, floor_id, category_code, name, status, position_x, position_y)
  select 1, 1, 2, 'retail', 'chaos-' || i, 'published', 100 + i % 800, 100 + i % 500
  from generate_series(1, 2000) i;" > /dev/null 2>&1
T0=$(date +%s%N)
LIST=$(_get "http://127.0.0.1:8945/api/v1/pois?venue_id=1&status=published&page_size=100")
T1=$(date +%s%N)
MS=$(( (T1 - T0) / 1000000 ))
if [ $MS -lt 3000 ]; then ok "⑥ 大数据量分页 ${MS}ms < 3s"; else fail "⑥ 分页 ${MS}ms"; fi
docker exec sage-postgres psql -U sage -d sage -c "
  delete from pois where name like 'chaos-%';" > /dev/null 2>&1

echo ""
echo "====== 结果：$PASS 通过 / $FAIL 失败 ======"
[ $FAIL -eq 0 ] && echo "全部通过" || exit 1
