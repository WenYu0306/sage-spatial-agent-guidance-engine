"""八工具集成测试（真库 + ASGI 内联服务）：逐工具验证 + 指纹去重。"""

from __future__ import annotations

import os
import uuid

import httpx
import psycopg
import pytest
from agent_orchestrator.tools import ToolContext, run_tool
from knowledge_rag.app import app as knowledge_app
from route_engine.app import app as route_app


class _SyncASGI(httpx.BaseTransport):
    """把 ASGITransport（async-only）包成同步 transport，测试免起端口。"""

    def __init__(self, app):
        self._inner = httpx.ASGITransport(app=app)

    def handle_request(self, request):
        import asyncio

        loop = asyncio.new_event_loop()
        try:
            response = loop.run_until_complete(self._inner.handle_async_request(request))
            body = loop.run_until_complete(response.aread())
            return httpx.Response(status_code=response.status_code,
                                  headers=response.headers, content=body, request=request)
        finally:
            loop.close()


def _dsn() -> str:
    return os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)


@pytest.fixture(scope="module")
def ids():
    with psycopg.connect(_dsn()) as conn, conn.cursor() as cur:
        cur.execute("select id from tenants where code='shanqueli-demo'")
        tid = cur.fetchone()[0]
        cur.execute(
            "select v.id from venues v join tenants t on t.id=v.tenant_id "
            "where t.code='shanqueli-demo'"
        )
        vid = cur.fetchone()[0]
        cur.execute("select id from floors where venue_id=%s and level=1", (vid,))
        f1 = cur.fetchone()[0]
    return tid, vid, f1


@pytest.fixture
def ctx(ids):
    tid, vid, f1 = ids
    return ToolContext(
        tenant_id=tid, venue_id=vid, tenant_code="shanqueli-demo",
        venue_name="山雀里·栖云广场", dsn=_dsn(),
        http_route=httpx.Client(transport=_SyncASGI(route_app),
                                base_url="http://route.test"),
        http_knowledge=httpx.Client(transport=_SyncASGI(knowledge_app),
                                    base_url="http://kg.test"),
        position={"x": 600, "y": 400, "floor_id": f1},
    )


def test_poi_search_by_category(ctx):
    r = run_tool("poi.search", {"category": "火锅"}, ctx)
    names = {i["name"] for i in r.data["items"]}
    assert {"云雀灶火锅", "石浪火锅", "灶门炭火锅"} <= names


def test_poi_search_by_scene_tag(ctx):
    r = run_tool("poi.search", {"scene_tag": "约会"}, ctx)
    assert r.ok and len(r.data["items"]) >= 1


def test_facility_nearest_same_floor_first(ctx):
    r = run_tool("facility.nearest", {"facility": "卫生间"}, ctx)
    assert r.ok and r.data["items"]
    assert r.data["items"][0]["same_floor"] is True


def test_route_plan_cross_floor(ctx):
    r = run_tool("route.plan", {"from_poi_name": "云雀优选超市",
                                "to_poi_name": "巨幕星云影院"}, ctx)
    assert r.ok and "error_code" not in (r.data or {})
    assert len(r.data["segments"]) >= 8
    labels = {v["label"] for v in r.data["nodes"].values()}
    assert "云雀优选超市" in labels and "巨幕星云影院" in labels


def test_promotion_list(ctx):
    r = run_tool("promotion.list", {}, ctx)
    assert len(r.data["activities"]) == 6 and len(r.data["coupons"]) == 4


def test_coupon_claim_idempotent(ctx):
    anon = f"test-{uuid.uuid4().hex[:8]}"
    r1 = run_tool("coupon.claim", {"coupon_title": "满 100 减 20", "anonymous_id": anon}, ctx)
    r2 = run_tool("coupon.claim", {"coupon_title": "满 100 减 20", "anonymous_id": anon}, ctx)
    assert r1.data["claimed"] is True and r1.data["duplicate"] is False
    assert r2.data["claimed"] is True and r2.data["duplicate"] is True, "幂等：不重复发放"


def test_knowledge_query_provenance(ctx):
    r = run_tool("knowledge.query", {"query": "商场几点关门", "threshold": 0.0}, ctx)
    assert r.ok and r.data["items"]
    assert all(i["document_id"] > 0 for i in r.data["items"])


def test_recommend_rank_temporary_by_distance(ctx, ids):
    with psycopg.connect(_dsn()) as conn, conn.cursor() as cur:
        cur.execute("select id from pois where name in ('云雀优选超市', '巨幕星云影院')")
        pair = [r[0] for r in cur.fetchall()]
    r = run_tool("recommend.rank", {"candidates": pair}, ctx)
    assert r.ok and r.data["temporary"] is True
    assert r.data["ranked"][0]["name"] == "云雀优选超市", "F1 位置距 B1 超市坐标更近"


def test_fingerprint_dedup(ctx):
    seen: set[str] = set()
    args = {"category": "火锅"}
    r1 = run_tool("poi.search", args, ctx, seen=seen)
    r2 = run_tool("poi.search", dict(args), ctx, seen=seen)
    assert r1.ok and not r2.ok and r2.error_code == 3005


def test_unknown_tool_rejected(ctx):
    assert run_tool("no.such", {}, ctx).error_code == 9999
