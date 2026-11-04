"""HTTP 服务测试：SSE 事件序列、422、越权 1003、trace 接口（桩 chat + 真工具）。"""

from __future__ import annotations

import json
import uuid

import httpx
import psycopg
import pytest
from agent_orchestrator.app import create_app
from fastapi.testclient import TestClient
from route_engine.app import app as route_app


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
