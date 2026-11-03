"""单模块演示：拉起真兄弟服务（子进程，模块间走 HTTP）+ 真库 + make_provider。

cd packages/agent-orchestrator && make demo —— 单命令跑两轮问答并打印 trace 摘要。
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import httpx
import psycopg
from platform_core.config import Settings
from platform_core.llm import make_provider

from .graph import build_graph
from .tools import ToolContext

DEMO_ROUTE_PORT = 18942
DEMO_KG_PORT = 18943
_PROMPTS = Path(__file__).resolve().parents[1] / "prompts"


def _start_services() -> tuple[subprocess.Popen, subprocess.Popen]:
    """兄弟模块以真 HTTP 服务拉起（架构纪律：模块间走 HTTP，不跨包 import）。"""
    route = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "route_engine.app:app", "--port", str(DEMO_ROUTE_PORT)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    kg = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "knowledge_rag.app:app", "--port", str(DEMO_KG_PORT)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for port in (DEMO_ROUTE_PORT, DEMO_KG_PORT):
        for _ in range(40):
            try:
                if httpx.get(f"http://localhost:{port}/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.3)
        else:
            route.terminate()
            kg.terminate()
            msg = "兄弟服务 %d 未就绪（先 make migrate && make seed && make ingest）" % port
            raise RuntimeError(msg)
    return route, kg


def _scalar(sql: str, params: tuple = ()) -> int:
    with psycopg.connect(Settings.from_env().database_url) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()[0]


def _run_turns() -> None:
    ctx = ToolContext(
        tenant_id=_scalar("select id from tenants where code='shanqueli-demo'"),
        venue_id=_scalar(
            "select v.id from venues v join tenants t on t.id=v.tenant_id "
            "where t.code='shanqueli-demo'"),
        tenant_code="shanqueli-demo", venue_name="山雀里·栖云广场",
        dsn=Settings.from_env().database_url,
        http_route=httpx.Client(base_url=f"http://localhost:{DEMO_ROUTE_PORT}", timeout=5),
        http_knowledge=httpx.Client(base_url=f"http://localhost:{DEMO_KG_PORT}", timeout=5),
        position={"x": 600, "y": 400, "floor_id": _scalar(
            "select f.id from floors f join venues v on v.id=f.venue_id "
            "join tenants t on t.id=v.tenant_id "
            "where t.code='shanqueli-demo' and f.level=1")},
    )
    graph = build_graph()
    provider = make_provider()
    for message in ("我想吃火锅", "带我去电影院"):
        session_id = _scalar(
            "insert into agent_sessions (tenant_id, venue_id, channel) "
            "values (%s, %s, 'screen') returning id", (ctx.tenant_id, ctx.venue_id))
        message_id = _scalar(
            "insert into agent_messages (session_id, tenant_id, role, content) "
            "values (%s, %s, 'user', %s) returning id", (session_id, ctx.tenant_id, message))
        final = graph.invoke(
            {"tenant_id": ctx.tenant_id, "venue_id": ctx.venue_id, "message": message,
             "trace_id": f"tr_demo{session_id}", "session_id": session_id,
             "message_id": message_id},
            {"configurable": {"thread_id": session_id, "ctx": ctx, "provider": provider,
                              "prompts_dir": _PROMPTS, "anonymous_id": "demo"},
             "recursion_limit": 25},
        )
        print(f"\n顾客：{message}")
        print(f"助手：{final['answer']}")
        for card in final["cards"]:
            print(f"  卡片[{card['type']}]：{json.dumps(card, ensure_ascii=False)[:100]}")
        print(f"  引用：{len(final.get('citations', []))} 条 | degraded={final['degraded']}")
    print("\n（demo 完成；同库 trace 可在 /trace.html 查看）")


def main() -> int:
    route_proc, kg_proc = _start_services()
    try:
        _run_turns()
    finally:
        route_proc.terminate()
        kg_proc.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
