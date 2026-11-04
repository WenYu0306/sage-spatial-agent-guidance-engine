"""八工具集成测试（真库 + ASGI 内联服务）：逐工具验证 + 指纹去重。"""

from __future__ import annotations

import os
import uuid

import httpx
import psycopg
import pytest
from agent_orchestrator.tools import ToolContext, run_tool
from knowledge_rag.app import app as knowledge_app
from recommender.app import create_app as recommender_create_app
from route_engine.app import app as route_app

os.environ.setdefault("SAGE_TIME_OVERRIDE", "2026-11-04T12:00:00")  # 营业状态时间注入


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


@pytest.fixture(scope="module")
def ctx(ids):
    tid, vid, f1 = ids
    return ToolContext(
        tenant_id=tid, venue_id=vid, tenant_code="shanqueli-demo",
        venue_name="山雀里·栖云广场", dsn=_dsn(),
        http_route=httpx.Client(transport=_SyncASGI(route_app),
                                base_url="http://route.test"),
        http_knowledge=httpx.Client(transport=_SyncASGI(knowledge_app),
                                    base_url="http://kg.test"),
        http_recommender=httpx.Client(
            transport=_SyncASGI(recommender_create_app(dsn=_dsn())),
            base_url="http://rec.test"),
        http_content=_content_client(),
        position={"x": 600, "y": 400, "floor_id": f1},
    )


def test_poi_search_by_category(ctx):
    r = run_tool("poi.search", {"category": "火锅"}, ctx)
    names = {i["name"] for i in r.data["items"]}
    assert {"云雀灶火锅", "石浪火锅", "灶门炭火锅"} <= names


def test_poi_search_by_scene_tag(ctx):
    r = run_tool("poi.search", {"scene_tag": "约会"}, ctx)
    assert r.ok and len(r.data["items"]) >= 1


def test_poi_search_scene_tag_bidirectional_match(ctx):
    """场景词与标签双向包含（PRD E04/E13 类问句）："家庭聚餐"须命中 tag[聚餐]。"""
    r = run_tool("poi.search", {"scene_tag": "家庭聚餐"}, ctx)
    assert r.ok and len(r.data["items"]) >= 1, "家庭聚餐应命中聚餐类店铺"
    r2 = run_tool("poi.search", {"scene_tag": "情侣约会"}, ctx)
    assert r2.ok and len(r2.data["items"]) >= 1, "情侣约会应命中约会类店铺"


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
    # 该券可能被其他验收领至售罄：测试自带库存重置（幂等语义与数据量解耦）
    with psycopg.connect(_dsn()) as conn, conn.cursor() as cur:
        cur.execute("update coupons set claimed_qty=0 where title like '满 100 减 20%'")
        conn.commit()
    r1 = run_tool("coupon.claim", {"coupon_title": "满 100 减 20", "anonymous_id": anon}, ctx)
    r2 = run_tool("coupon.claim", {"coupon_title": "满 100 减 20", "anonymous_id": anon}, ctx)
    assert r1.data["claimed"] is True and r1.data["duplicate"] is False, r1.data
    assert r2.data["claimed"] is True and r2.data["duplicate"] is True, "幂等：不重复发放"


def test_knowledge_query_provenance(ctx):
    r = run_tool("knowledge.query", {"query": "商场几点关门", "threshold": 0.0}, ctx)
    assert r.ok and r.data["items"]
    assert all(i["document_id"] > 0 for i in r.data["items"])


def test_recommend_rank_via_m7(ctx, ids):
    """M7 落地后 recommend.rank 走 HTTP 打分：带八因子明细与理由。"""
    with psycopg.connect(_dsn()) as conn, conn.cursor() as cur:
        cur.execute("select id from pois where name in ('云雀优选超市', '巨幕星云影院')")
        pair = [r[0] for r in cur.fetchall()]
    r = run_tool("recommend.rank", {"candidates": pair}, ctx)
    assert r.ok and "temporary" not in r.data
    top = r.data["ranked"][0]
    assert len(top["factors"]) == 8 and top["reasons"]
    assert all("floor" in row for row in r.data["ranked"]), "卡片楼层信息不丢"


def test_recommend_rank_falls_back_to_distance(ctx, ids):
    """M7 不可用时降级为距离排序（PRD 8.2 声明的降级路径，temporary 标记）。"""
    with psycopg.connect(_dsn()) as conn, conn.cursor() as cur:
        cur.execute("select id from pois where name in ('云雀优选超市', '巨幕星云影院')")
        pair = [r[0] for r in cur.fetchall()]

    class _Down(httpx.BaseTransport):
        def handle_request(self, request):
            raise httpx.ConnectError("recommender down")

    from dataclasses import replace

    down_ctx = replace(ctx, http_recommender=httpx.Client(
        transport=_Down(), base_url="http://rec.test"))
    r = run_tool("recommend.rank", {"candidates": pair}, down_ctx)
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


def test_route_plan_by_poi_id(ctx):
    """路线目标支持 poi_id 直取（回归：按名 ilike 在并列 hot_score 时随机选层，
    用户在 F1 却被指引去 B1 卫生间）。"""
    import psycopg

    with psycopg.connect(ctx.dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "select p.id from pois p where p.tenant_id=%s and p.venue_id=%s "
            "and p.name='F1 卫生间'", (ctx.tenant_id, ctx.venue_id))
        pid = cur.fetchone()[0]
    r = run_tool("route.plan", {"to_poi_id": pid,
                                "from_poi_name": "汀兰咖啡"}, ctx)
    assert r.ok, r.data
    labels = {v["label"] for v in r.data["nodes"].values()}
    assert "F1 卫生间" in labels, f"目标应是 F1 卫生间，实际 {labels}"


def test_nearest_and_route_plan_shares_target():
    """计划步骤：路线目标必须取 facility.nearest 实际选中的 poi（同层优先），
    不得按名字独立解析（回归：说在 F1 有厕所却指路 B1）。"""
    from agent_orchestrator.graph import _PLANNED_STEPS
    view = {"intent": {"slots": {"category": "卫生间", "poi_name": None,
                                 "scene_tag": None, "need_route": True}},
            "tool_results": {"facility.nearest": {"items": [
                {"poi_id": 77, "name": "F1 卫生间", "floor": "F1"},
                {"poi_id": 31, "name": "B1 卫生间", "floor": "B1"},
            ]}}}
    steps = _PLANNED_STEPS["nearest_and_route"](view, None)
    lazy = steps[-1]
    assert callable(lazy), "路线步骤应为惰性 callable（依赖前一步输出）"
    route_args = dict(lazy(view["tool_results"])[1])
    assert route_args.get("to_poi_id") == 77, f"应直取最近设施的 poi_id，实为 {route_args}"
