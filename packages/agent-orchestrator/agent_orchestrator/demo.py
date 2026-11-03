"""单模块演示：进程内拉起 route/knowledge（ASGI 内联）+ 真库 + make_provider，跑两轮问答。

外部依赖不落端口：兄弟服务经内联 ASGI transport 调用（与测试同机制）。
"""

from __future__ import annotations

import asyncio
import json

import httpx
import psycopg
from platform_core.config import Settings

from .graph import build_graph
from .tools import ToolContext


def _sync_asgi(app):
    class T(httpx.BaseTransport):
        def __init__(self, app):
            self._inner = httpx.ASGITransport(app=app)

        def handle_request(self, request):
            loop = asyncio.new_event_loop()
            try:
                resp = loop.run_until_complete(self._inner.handle_async_request(request))
                body = loop.run_until_complete(resp.aread())
                return httpx.Response(status_code=resp.status_code,
                                      headers=resp.headers, content=body, request=request)
            finally:
                loop.close()

    return T(app)


def main() -> int:
    from knowledge_rag.app import app as knowledge_app
    from platform_core.llm import make_provider
    from route_engine.app import app as route_app

    settings = Settings.from_env()
    ctx = ToolContext(
        tenant_id=_scalar("select id from tenants where code='shanqueli-demo'"),
        venue_id=_scalar(
            "select v.id from venues v join tenants t on t.id=v.tenant_id "
            "where t.code='shanqueli-demo'"),
        tenant_code="shanqueli-demo", venue_name="山雀里·栖云广场",
        dsn=settings.database_url,
        http_route=httpx.Client(transport=_sync_asgi(route_app), base_url="http://route.test"),
        http_knowledge=httpx.Client(transport=_sync_asgi(knowledge_app), base_url="http://kg.test"),
        position={"x": 600, "y": 400, "floor_id": _scalar(
            "select id from floors where level=1 "
            "and venue_id=(select v.id from venues v join tenants t on t.id=v.tenant_id "
            "where t.code='shanqueli-demo')")},
    )
    graph = build_graph()
    provider = make_provider()
    for message in ("我想吃火锅", "带我去电影院"):
        session_id = _scalar(
            "insert into agent_sessions (tenant_id, venue_id, channel) "
            "values ((select id from tenants where code='shanqueli-demo'), "
            "(select v.id from venues v join tenants t on t.id=v.tenant_id "
            "where t.code='shanqueli-demo'), 'screen') returning id")
        message_id = _scalar(
            "insert into agent_messages (session_id, tenant_id, role, content) "
            "values (%s, (select id from tenants where code='shanqueli-demo'), 'user', %s) "
            "returning id", (session_id, message))
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
    return 0


def _scalar(sql: str, params: tuple = ()) -> int:
    settings = Settings.from_env()
    with psycopg.connect(settings.database_url) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()[0]


from pathlib import Path  # noqa: E402

_PROMPTS = Path(__file__).resolve().parents[1] / "prompts"

if __name__ == "__main__":
    raise SystemExit(main())
