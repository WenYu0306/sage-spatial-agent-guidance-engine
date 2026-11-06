"""图编排集成测试（桩 chat + 真工具/真库）：全链路、预算降级、trace 落库。"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import httpx
import psycopg
import pytest
from agent_orchestrator.graph import build_graph
from agent_orchestrator.tools import ToolContext
from knowledge_rag.app import app as knowledge_app
from route_engine.app import app as route_app

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


class FakeChat:
    """意图+生成双用桩：按问题关键词返回意图 JSON；生成返回固定文案。"""

    def chat(self, messages, **_kw):
        text = messages[-1]["content"]
        if any(m["role"] == "user" and "顾客说" in m["content"] for m in messages):
            return "为你找到云雀灶火锅、石浪火锅，都在二层。", {"tokens_in": 10, "tokens_out": 12}
        if "火锅" in text:
            intent = "poi_search"
        elif "关门" in text or "几点" in text:
            intent = "venue_info"
        else:
            intent = "fallback"
        return json.dumps({"intent": intent,
                           "slots": {"category": "火锅" if intent == "poi_search" else None,
                                     "scene_tag": None, "poi_name": None,
                                     "need_route": False}}), {"tokens_in": 5, "tokens_out": 5}


def _dsn() -> str:
    import os

    return os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)


@pytest.fixture(scope="module")
def base_ids():
    with psycopg.connect(_dsn()) as conn, conn.cursor() as cur:
        cur.execute("select id from tenants where code='shanqueli-demo'")
        tid = cur.fetchone()[0]
        cur.execute(
            "select v.id from venues v join tenants t on t.id=v.tenant_id "
            "and v.name='山雀里·栖云广场' "
            "where t.code='shanqueli-demo'"
        )
        vid = cur.fetchone()[0]
        cur.execute("select id from floors where venue_id=%s and level=1", (vid,))
        f1 = cur.fetchone()[0]
    return tid, vid, f1


def _content_client(_dsn=None):
    """内联 content 服务（M8）注入。缺省读 DATABASE_URL。"""
    import os

    dsn = (_dsn or os.environ.get("DATABASE_URL") or "").replace(
        "postgresql+psycopg://", "postgresql://", 1)
    import asyncio

    import httpx
    from content_service.app import create_app as content_create_app

    app = content_create_app(dsn=dsn)

    class _Sync(httpx.BaseTransport):
        def __init__(self, a):
            self.i = httpx.ASGITransport(app=a)

        def handle_request(self, request):
            loop = asyncio.new_event_loop()
            try:
                resp = loop.run_until_complete(self.i.handle_async_request(request))
                body = loop.run_until_complete(resp.aread())
                return httpx.Response(resp.status_code, headers=resp.headers,
                                      content=body, request=request)
            finally:
                loop.close()

    return httpx.Client(transport=_Sync(app), base_url="http://c")


def _invoke(base_ids, message: str):
    tid, vid, f1 = base_ids
    ctx = ToolContext(
        tenant_id=tid, venue_id=vid, tenant_code="shanqueli-demo",
        venue_name="山雀里·栖云广场", dsn=_dsn(),
        http_route=httpx.Client(transport=_sync_asgi(route_app), base_url="http://r"),
        http_knowledge=httpx.Client(transport=_sync_asgi(knowledge_app), base_url="http://k"),
        http_content=_content_client(),
        position={"x": 600, "y": 400, "floor_id": f1},
    )
    provider = FakeChat()
    graph = build_graph()
    trace_id = "tr_" + uuid.uuid4().hex[:12]

    # 造 session + message（trace 外键需要）
    with psycopg.connect(_dsn()) as conn, conn.cursor() as cur:
        cur.execute(
            "insert into agent_sessions (tenant_id, venue_id, channel) "
            "values (%s, %s, 'screen') returning id", (tid, vid),
        )
        session_id = cur.fetchone()[0]
        cur.execute(
            "insert into agent_messages (session_id, tenant_id, role, content) "
            "values (%s, %s, 'user', %s) returning id", (session_id, tid, message),
        )
        message_id = cur.fetchone()[0]
    config = {"configurable": {"thread_id": trace_id, "ctx": ctx,
                                "provider": provider, "prompts_dir": PROMPTS_DIR},
              "recursion_limit": 25}
    state = {"tenant_id": tid, "venue_id": vid, "message": message,
             "trace_id": trace_id, "session_id": session_id, "message_id": message_id}
    final = graph.invoke(state, config)
    return final, trace_id


def _sync_asgi(app):
    class T(httpx.BaseTransport):
        def __init__(self, app):
            self._inner = httpx.ASGITransport(app=app)

        def handle_request(self, request):
            import asyncio

            loop = asyncio.new_event_loop()
            try:
                resp = loop.run_until_complete(self._inner.handle_async_request(request))
                body = loop.run_until_complete(resp.aread())
                return httpx.Response(status_code=resp.status_code, headers=resp.headers,
                                      content=body, request=request)
            finally:
                loop.close()

    return T(app)


def test_full_flow_poi_search(base_ids):
    final, trace_id = _invoke(base_ids, "我想吃火锅")
    assert final["intent"]["intent"] == "poi_search"
    assert "poi.search" in final["tool_results"]
    assert final["answer"], "必须有回答"
    assert any(c["type"] == "poi_list" for c in final["cards"])
    assert final["degraded"] is False
    with psycopg.connect(_dsn()) as conn, conn.cursor() as cur:
        cur.execute("select step_type, tool_code from agent_traces where trace_id=%s "
                    "order by step_index", (trace_id,))
        rows = cur.fetchall()
    assert rows[0][0] == "intent_parse"
    assert any(r[0] == "tool_call" and r[1] == "poi.search" for r in rows)
    assert rows[-1][0] == "generate"


def test_tool_trace_latency_is_measured(base_ids):
    """审查 B4：t0 曾放在 run_tool 之后，tool_call 时延恒 0ms，监控五指标失真。"""
    _final, trace_id = _invoke(base_ids, "我想吃火锅")
    with psycopg.connect(_dsn()) as conn, conn.cursor() as cur:
        cur.execute("select tool_code, latency_ms from agent_traces where trace_id=%s "
                    "and step_type='tool_call'", (trace_id,))
        lats = dict(cur.fetchall())
    assert lats, "应有 tool_call 步骤"
    assert lats.get("poi.search", 0) > 0, f"poi.search 时延必须为真实测量值，实测 {lats}"


def test_venue_info_uses_knowledge(base_ids):
    final, _tid = _invoke(base_ids, "商场几点关门")
    assert "knowledge.query" in final["tool_results"]
    assert final["citations"], "venue_info 必须带引用"


def test_fallback_has_no_hard_coded_answer(base_ids):
    final, _tid = _invoke(base_ids, "今天天气怎么样")
    assert final["intent"]["intent"] == "fallback"


def test_hallucinated_store_name_degrades(base_ids):
    """编造名单外的店名 → 记 warning、降级为列表卡片回答（PRD 8.3 规则 1）。"""
    tid, vid, f1 = base_ids
    ctx = ToolContext(
        tenant_id=tid, venue_id=vid, tenant_code="shanqueli-demo",
        venue_name="山雀里·栖云广场", dsn=_dsn(),
        http_route=httpx.Client(transport=_sync_asgi(route_app), base_url="http://r"),
        http_knowledge=httpx.Client(transport=_sync_asgi(knowledge_app), base_url="http://k"),
        http_content=_content_client(),
        position={"x": 600, "y": 400, "floor_id": f1},
    )

    class LyingChat(FakeChat):
        def chat(self, messages, **_kw):
            if any("顾客说" in m["content"] for m in messages if m["role"] == "user"):
                return "推荐你去冰晶甜品屋，超好吃。", {"tokens_in": 1, "tokens_out": 1}
            return super().chat(messages, **_kw)

    graph = build_graph()
    with psycopg.connect(_dsn()) as conn, conn.cursor() as cur:
        cur.execute("insert into agent_sessions (tenant_id, venue_id) values (%s,%s) returning id",
                    (tid, vid))
        session_id = cur.fetchone()[0]
        cur.execute("insert into agent_messages (session_id, tenant_id, role, content) "
                    "values (%s,%s,'user','吃甜品') returning id", (session_id, tid))
        message_id = cur.fetchone()[0]
    config = {"configurable": {"thread_id": "tr_" + uuid.uuid4().hex[:12], "ctx": ctx,
                               "provider": LyingChat(), "prompts_dir": PROMPTS_DIR},
              "recursion_limit": 25}
    final = graph.invoke({"tenant_id": tid, "venue_id": vid, "message": "吃甜品",
                          "trace_id": "tr_" + uuid.uuid4().hex[:12],
                          "session_id": session_id, "message_id": message_id}, config)
    assert final["degraded"] is True
    assert "冰晶甜品屋" not in final["answer"], "编造店名不得出现在最终回答"


def test_trace_clip_always_valid_json():
    """超长工具输出截断后必须仍是合法 JSON（回归：[:2000] 盲切导致 3001）。"""
    import json as _json

    from agent_orchestrator.graph import _clip
    big = {"items": [{"name": "店" * 30, "tags": ["标签"], "hot": i} for i in range(12)]}
    raw = _clip(big)
    assert len(raw) <= 2100
    assert _json.loads(raw)  # 可解析
    small = _clip({"items": []})
    assert _json.loads(small) == {"items": []}


def test_unknown_poi_names_skips_question_echo():
    """用户话术回声（"附近咖啡店"）不是编造店名——校验器不得误报（回归 E17）。"""
    from agent_orchestrator.graph import _unknown_poi_names
    assert _unknown_poi_names("附近咖啡店有这些：汀兰咖啡。", {"汀兰咖啡"}) == []


def test_known_poi_names_collects_promotion_store_names():
    """优惠结果中的关联门店名必须进入白名单（回归 E05：券关联店被误判幻觉）。"""
    from agent_orchestrator.graph import _known_poi_names
    names = _known_poi_names({
        "promotion.list": {"coupons": [
            {"title": "灶门炭火锅 50 元代金券", "poi_name": "灶门炭火锅"},
            {"title": "全场满 100 减 20", "poi_name": None},
        ]},
    })
    assert "灶门炭火锅" in names

def test_unknown_poi_names_ignores_function_phrases():
    """审查 U1 录制期实锤：回答含「…建议到店…」等句式时，功能词残片被当假店名误杀。"""
    from agent_orchestrator.graph import _unknown_poi_names
    known = {"云隙咖啡", "野莓茶集", "白桦西餐"}
    assert _unknown_poi_names("情侣约会建议到店体验更好。", known) == []
    assert _unknown_poi_names("可以直接到店品尝，乘直梯前往。", known) == []
    # 真编造仍拦截
    assert _unknown_poi_names("推荐幻影火锅店。", known) == ["幻影火锅店"]
