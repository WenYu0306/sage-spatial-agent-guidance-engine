"""HTTP 服务测试：SSE 事件序列、422、越权 1003、trace 接口（桩 chat + 真工具）。"""

from __future__ import annotations

import json
import uuid

import httpx


def _content_client(_dsn=None):
    """内联 content 服务（M8）：工具 HTTP 化后的测试注入点（CI 密闭、不依赖 8945）。"""
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
import psycopg  # noqa: E402
import pytest  # noqa: E402
from agent_orchestrator.app import create_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from route_engine.app import app as route_app  # noqa: E402


class _SyncASGI(httpx.BaseTransport):
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


class FakeChat:
    seen_histories = []

    def chat(self, messages, **_kw):
        FakeChat.seen_histories.append(messages)
        if any("顾客说" in m["content"] for m in messages if m["role"] == "user"):
            return "为你找到云雀灶火锅，在二层。", {"tokens_in": 1, "tokens_out": 1}
        payload = json.dumps({"intent": "poi_search",
                              "slots": {"category": "火锅", "scene_tag": None,
                                        "poi_name": None, "need_route": False}})
        return payload, {"tokens_in": 1, "tokens_out": 1}


@pytest.fixture(scope="module")
def client():
    app = create_app(provider=FakeChat(), checkpointer=None)
    # 注入内联服务 transport：测试免起端口
    app.state.http_route = httpx.Client(transport=_SyncASGI(route_app), base_url="http://r")
    app.state.http_content = _content_client()
    return TestClient(app)


def _venue_ids():
    import os

    dsn = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "select v.id from venues v join tenants t on t.id=v.tenant_id "
            "where t.code='shanqueli-demo'"
        )
        return cur.fetchone()[0], dsn


def test_sse_event_sequence(client):
    vid, _ = _venue_ids()
    with client.stream(
        "POST", "/api/v1/agent/chat",
        json={"venue_id": vid, "message": "我想吃火锅"},
    ) as resp:
        assert resp.status_code == 200
        text = "".join(chunk for chunk in resp.iter_text())
    for ev in ("event: meta", "event: delta", "event: card", "event: done"):
        assert ev in text, f"缺 SSE 事件 {ev}"
    done_line = [ln for ln in text.splitlines() if ln.startswith("data: ") and "status" in ln][-1]
    assert '"status": "ok"' in done_line or '"status":"ok"' in done_line
    assert "voice_channel" not in text  # 冻结字段只在协议文档，SSE 不发


def test_chat_emits_ai_query_event(client):
    """M9 打点：问答完成后写 ai_query 事件（含 intent/latency/degraded/tool_count）。"""
    vid, dsn = _venue_ids()
    marker = f"evt-test-{uuid.uuid4().hex[:8]}"
    with client.stream(
        "POST", "/api/v1/agent/chat",
        json={"venue_id": vid, "message": "我想吃火锅", "context": {"event_id_marker": marker}},
    ) as resp:
        assert resp.status_code == 200
        text = "".join(chunk for chunk in resp.iter_text())
    meta = [ln for ln in text.splitlines() if ln.startswith("data: ")][0]
    session_id = json.loads(meta[6:])["session_id"]
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "select payload from events where event_type='ai_query' and session_id=%s "
            "order by id desc limit 1", (session_id,))
        row = cur.fetchone()
    assert row, "问答完成应写 ai_query 事件"
    payload = row[0]
    assert {"intent", "latency_ms", "degraded", "tool_count"} <= set(payload)


def test_message_length_422(client):
    vid, _ = _venue_ids()
    r = client.post("/api/v1/agent/chat", json={"venue_id": vid, "message": "长" * 501})
    assert r.status_code == 422


def test_venue_tenant_mismatch_1003(client):
    r = client.post("/api/v1/agent/chat", json={"venue_id": 999999, "message": "hi"})
    assert r.status_code == 200 and r.json()["error_code"] == 1003


def test_trace_endpoint_returns_steps(client):
    vid, dsn = _venue_ids()
    with client.stream("POST", "/api/v1/agent/chat",
                       json={"venue_id": vid, "message": "我想吃火锅"}) as resp:
        text = "".join(chunk for chunk in resp.iter_text())
    meta = [ln for ln in text.splitlines() if ln.startswith("data: ")][0]
    session_id = json.loads(meta[6:])["session_id"]
    r = client.get(f"/api/v1/agent/sessions/{session_id}/trace")
    steps = r.json()["steps"]
    assert r.status_code == 200 and len(steps) >= 2
    assert steps[0]["step_type"] == "intent_parse"
    assert any(s["step_type"] == "tool_call" for s in steps)


def test_multi_turn_history_injected(client):
    """同 session 第二轮：意图解析必须收到此前消息（thread_id=session_id + 历史）。"""
    vid, _ = _venue_ids()
    with client.stream("POST", "/api/v1/agent/chat",
                       json={"venue_id": vid, "message": "我想吃火锅"}) as resp:
        text = "".join(chunk for chunk in resp.iter_text())
    meta = [ln for ln in text.splitlines() if ln.startswith("data: ")][0]
    session_id = json.loads(meta[6:])["session_id"]
    FakeChat.seen_histories.clear()
    with client.stream("POST", "/api/v1/agent/chat",
                       json={"venue_id": vid, "session_id": session_id,
                             "message": "这家店现在营业吗"}) as resp:
        "".join(chunk for chunk in resp.iter_text())
    assert any(
        any("我想吃火锅" in m["content"] for m in msgs if m["role"] == "user")
        for msgs in FakeChat.seen_histories
    ), "第二轮意图解析必须携带首轮历史"


class FakeRecommendChat:
    """poi_recommend 意图桩：验证 rank 步骤拿到同轮 search 的候选。"""

    def chat(self, messages, **_kw):
        if any("顾客说" in m["content"] for m in messages if m["role"] == "user"):
            return "为你推荐这几家。", {"tokens_in": 1, "tokens_out": 1}
        payload = json.dumps({"intent": "poi_recommend",
                              "slots": {"category": "火锅", "scene_tag": "聚餐",
                                        "poi_name": None, "need_route": False}})
        return payload, {"tokens_in": 1, "tokens_out": 1}


def test_rank_step_receives_same_turn_search_candidates():
    """同轮依赖：rank 必须拿到本轮 poi.search 的候选（回归：曾读到冻结 state 而恒空）。"""
    app = create_app(provider=FakeRecommendChat(), checkpointer=None)
    client = TestClient(app)
    vid, _ = _venue_ids()
    with client.stream(
        "POST", "/api/v1/agent/chat",
        json={"venue_id": vid, "message": "推荐适合聚餐的火锅"},
    ) as resp:
        assert resp.status_code == 200
        text = "".join(chunk for chunk in resp.iter_text())
    sid = None
    for block in text.split("\n\n"):
        if block.startswith("event: meta"):
            sid = json.loads(block.split("data: ", 1)[1])["session_id"]
    assert sid
    steps = client.get(f"/api/v1/agent/sessions/{sid}/trace").json()["steps"]
    rank_inputs = [s["input"] for s in steps
                   if s["step_type"] == "tool_call" and s["tool_code"] == "recommend.rank"]
    assert rank_inputs, "rank 步骤未执行"
    if not rank_inputs[0].get("candidates"):
        # CI 诊断：打印本轮全部工具输出（本地不可复现，环境差异定位用）
        import json as _json

        for st in steps:
            if st["step_type"] == "tool_call":
                print(f"[diag] {st['tool_code']}: {st['output']}")
    assert rank_inputs[0].get("candidates"), "rank 应拿到同轮 search 的候选"


def test_tool_budget_resets_per_turn():
    """checkpointer 跨轮残留回归：同一会话连问 7 轮，第 7 轮工具仍须执行
    （tool_calls 曾累计不清零，6 次后整轮被预算锁死）。"""
    app = create_app(provider=FakeRecommendChat(), checkpointer=None)
    client = TestClient(app)
    vid, _ = _venue_ids()
    sid = None
    last_trace_tools = None
    for i in range(7):
        with client.stream(
            "POST", "/api/v1/agent/chat",
            json={"venue_id": vid, "session_id": sid,
                  "message": f"推荐适合聚餐的火锅第{i}轮"},
        ) as resp:
            assert resp.status_code == 200
            text = "".join(chunk for chunk in resp.iter_text())
        for block in text.split("\n\n"):
            if block.startswith("event: meta"):
                sid = json.loads(block.split("data: ", 1)[1])["session_id"]
        steps = client.get(f"/api/v1/agent/sessions/{sid}/trace").json()["steps"]
        last_mid = max(s["message_id"] for s in steps)
        last_trace_tools = [s for s in steps
                            if s["step_type"] == "tool_call" and s["message_id"] == last_mid]
    assert last_trace_tools, "第 7 轮应有工具调用记录"


def test_make_checkpointer_prefers_postgres_and_never_silent():
    """回归（审计）：PostgresSaver 构造曾误用被静默换 InMemorySaver——
    可用库时必须真 Postgres；不可用时降级也必须发生（函数自身已留日志）。"""
    import os

    from agent_orchestrator.app import make_checkpointer
    from langgraph.checkpoint.memory import InMemorySaver

    dsn = os.environ["DATABASE_URL"]
    saver = make_checkpointer(dsn)
    assert not isinstance(saver, InMemorySaver), "真库可用时不得降级内存"
    bad = make_checkpointer("postgresql://nobody:nope@127.0.0.1:1/void")
    assert isinstance(bad, InMemorySaver), "连不上才允许降级"
