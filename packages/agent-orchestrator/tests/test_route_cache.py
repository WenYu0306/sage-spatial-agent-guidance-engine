"""M11 前置：chat 路线结果缓存 + GET /api/v1/route/{route_id}（PRD 642/690/872）。"""

from __future__ import annotations

import json

import httpx
import psycopg
import pytest
from agent_orchestrator.app import create_app
from route_engine.app import app as route_app


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
from fastapi.testclient import TestClient  # noqa: E402


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


class FakeNavChat:
    """navigate 意图桩：带我去某店 → route.plan 真跑（内联 route-engine）。"""

    def chat(self, messages, **_kw):
        if any("顾客说" in m["content"] for m in messages if m["role"] == "user"):
            return "已为你规划路线。", {"tokens_in": 1, "tokens_out": 1}
        payload = json.dumps({"intent": "navigate",
                              "slots": {"category": None, "scene_tag": None,
                                        "poi_name": "巨幕星云影院", "need_route": True}})
        return payload, {"tokens_in": 1, "tokens_out": 1}


@pytest.fixture(scope="module")
def client():
    app = create_app(provider=FakeNavChat(), checkpointer=None)
    app.state.http_route = httpx.Client(transport=_SyncASGI(route_app), base_url="http://r")
    app.state.http_content = _content_client()
    return TestClient(app)


def _venue_floor_ids() -> tuple[int, int]:
    import os

    dsn = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "select v.id, f.id from venues v join floors f on f.venue_id=v.id "
            "where v.tenant_id=(select id from tenants where code='shanqueli-demo') "
            "and f.name='F1' order by v.id limit 1")
        return cur.fetchone()


def _sse_events(text: str) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        ev, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                ev = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if ev and data is not None:
            out.append((ev, data))
    return out


def test_chat_emits_route_event_and_caches(client):
    vid, fid = _venue_floor_ids()
    with client.stream(
        "POST", "/api/v1/agent/chat",
        json={"venue_id": vid, "floor_id": fid, "message": "带我去巨幕星云影院",
              "context": {"position_x": 600, "position_y": 400}},
    ) as resp:
        assert resp.status_code == 200
        text = "".join(chunk for chunk in resp.iter_text())
    events = _sse_events(text)
    route_ev = [d for e, d in events if e == "route"]
    assert route_ev, f"缺 route 事件：{[e for e, _ in events]}"
    payload = route_ev[0]
    rid = payload["route_id"]
    assert payload["summary"]["distance_meter"] > 0
    assert payload["summary"]["eta_seconds"] > 0
    assert payload["nodes"] and payload["segments"]

    got = client.get(f"/api/v1/route/{rid}")
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["route_id"] == rid
    assert body["summary"] == payload["summary"]
    assert body["nodes"] == payload["nodes"]
    assert body["segments"] == payload["segments"]


def test_chat_route_planned_event_written(client):
    vid, fid = _venue_floor_ids()
    with client.stream(
        "POST", "/api/v1/agent/chat",
        json={"venue_id": vid, "floor_id": fid, "message": "带我去巨幕星云影院",
              "context": {"position_x": 600, "position_y": 400}},
    ) as resp:
        text = "".join(chunk for chunk in resp.iter_text())
    rid = [d for e, d in _sse_events(text) if e == "route"][0]["route_id"]
    import os

    dsn = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "select count(*) from events where event_type='route_plan' "
            "and payload->>'route_id'=%s", (str(rid),))
        assert cur.fetchone()[0] >= 1, "route_plan 埋点缺失"


def test_route_cache_miss_returns_2005(client):
    r = client.get("/api/v1/route/987654321")
    assert r.status_code == 404
    assert r.json()["error_code"] == 2005


def test_route_cache_rejects_bad_id(client):
    r = client.get("/api/v1/route/not-a-number")
    assert r.status_code == 422
