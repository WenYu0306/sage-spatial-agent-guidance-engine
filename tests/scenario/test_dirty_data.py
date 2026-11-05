"""13.2 脏数据体检（12 类，独立脏场地自建自拆——决策 1A）。

期望表现对照手册 13.2。首轮结果不美化：失败的按 13.3 铁律修复。
运行：uv run pytest tests/scenario/test_dirty_data.py -v
"""

from __future__ import annotations

import datetime as dt

import psycopg
import pytest
import httpx

BASE = "http://127.0.0.1:8945/api/v1"
DSN = None


def _dsn() -> str:
    import os

    return os.environ.get("DATABASE_URL", "").replace(
        "postgresql+psycopg://", "postgresql://", 1)


@pytest.fixture(scope="module")
def dirty():
    """脏数据场地：非标准楼层名 + 全套脏数据行；模块结束后整体级联清除。"""
    global DSN
    DSN = _dsn()
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute(
            "insert into venues (tenant_id, name, venue_type, address, timezone, status) "
            "values ((select id from tenants where code='shanqueli-demo'), "
            "'脏数据体检场地', 'mall', '测试', 'Asia/Shanghai', 'active') returning id")
        vid = cur.fetchone()[0]
        floors = {}
        for name, level in (("门诊楼3层", 3), ("住院部B区", -2), ("急诊2层", 2)):
            cur.execute(
                "insert into floors (tenant_id, venue_id, name, level, sort_order) "
                "values ((select id from tenants where code='shanqueli-demo'), %s, %s, %s, %s) "
                "returning id", (vid, name, level, level))
            floors[name] = cur.fetchone()[0]
        for fid in floors.values():
            cur.execute(
                "insert into map_layers (tenant_id, venue_id, floor_id, svg_url, "
                "width, height, scale_meter) values ((select id from tenants "
                "where code='shanqueli-demo'), %s, %s, '/static/maps/dirty.svg', "
                "1200, 800, 0.15)", (vid, fid))
        conn.commit()
    yield {"vid": vid, "floors": floors, "tid": _tid()}
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute("delete from coupon_claims where coupon_id in "
                    "(select id from coupons where venue_id=%s)", (vid,))
        cur.execute("delete from coupons where venue_id=%s", (vid,))
        cur.execute("delete from route_edges where venue_id=%s", (vid,))
        cur.execute("delete from route_nodes where venue_id=%s", (vid,))
        cur.execute("delete from pois where venue_id=%s", (vid,))
        cur.execute("delete from activities where venue_id=%s", (vid,))
        cur.execute("delete from floors where venue_id=%s", (vid,))
        cur.execute("delete from venues where id=%s", (vid,))
        conn.commit()


def _tid() -> int:
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute("select id from tenants where code='shanqueli-demo'")
        return cur.fetchone()[0]


def _poi(vid, floor_id, name, category="retail", status="published",
         x=500, y=400, hours="10:00-22:00", intro=None):
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute(
            "insert into pois (tenant_id, venue_id, floor_id, category_code, name, "
            "status, position_x, position_y, business_hours, intro) "
            "values ((select id from tenants where code='shanqueli-demo'), %s, %s, "
            "%s, %s, %s, %s, %s, %s::jsonb, %s) returning id",
            (vid, floor_id, category, name, status, x, y,
             json_hours(hours), intro))
        pid = cur.fetchone()[0]
        conn.commit()
    return pid


def json_hours(span):
    if span is None:
        return "null"
    return '{"mon": ["%s"], "sun": ["%s"]}' % (span, span)


def _node(vid, floor_id, x, y, node_type="waypoint"):
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute(
            "insert into route_nodes (tenant_id, venue_id, floor_id, node_type, x, y, "
            "accessible) values ((select id from tenants where code='shanqueli-demo'), "
            "%s, %s, %s, %s, %s, true) returning id", (vid, floor_id, node_type, x, y))
        nid = cur.fetchone()[0]
        conn.commit()
    return nid


def _edge(a, b, dist=50.0):
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        for f, t in ((a, b), (b, a)):
            cur.execute(
                "insert into route_edges (tenant_id, venue_id, from_node_id, to_node_id, "
                "edge_type, distance_meter, weight, accessible, is_bidirectional) "
                "values ((select id from tenants where code='shanqueli-demo'), "
                "(select venue_id from route_nodes where id=%s), %s, %s, 'walk', "
                "%s, %s, true, true)", (f, f, t, dist, dist / 1.2))
        conn.commit()


def _plan(start, goal):
    r = httpx.post("http://127.0.0.1:8942/route/plan", json={
        "tenant_code": "shanqueli-demo", "venue_name": "脏数据体检场地",
        "start_node_id": start, "goal_node_id": goal}, timeout=15)
    return r.json()


# ---------- ① 店名完全重复 ----------
def test_01_duplicate_names_listed_not_random(dirty):
    vid, f = dirty["vid"], dirty["floors"]["门诊楼3层"]
    _poi(vid, f, "同名体检科")
    _poi(vid, f, "同名体检科")
    r = httpx.get(f"{BASE}/pois", params={"venue_id": vid, "keyword": "同名体检科"})
    assert r.status_code == 200
    names = [i["name"] for i in r.json()["items"]]
    assert names.count("同名体检科") >= 2, f"重名店必须全部列出，实为 {names}"


# ---------- ② 营业时间跨天 ----------
def test_02_overnight_hours_open_at_1am():
    from content_service.app import _open_now
    # 动态取"昨天"的星期键：周四凌晨 1 点应命中周三条目上的跨天段
    now_1am = dt.datetime(2026, 11, 5, 1, 0)
    yday = (now_1am - dt.timedelta(days=1)).strftime("%a").lower()[:3]
    assert _open_now({yday: ["22:00-02:00"]}, now_1am) is True, \
        "跨天时段凌晨 1 点应判营业中"
    # 反例：当晚 21:00 尚未进入 22:00-02:00（首版合并查会在此假阳性）
    assert _open_now({"wed": ["22:00-02:00"]},
                     dt.datetime(2026, 11, 4, 21, 0)) is False, \
        "21:00 尚未进入 22:00-02:00 时段"
    # 反例：凌晨 3 点已出时段（02:00 结束）
    assert _open_now({yday: ["22:00-02:00"]},
                     dt.datetime(2026, 11, 5, 3, 0)) is False, \
        "03:00 已出跨天时段"


# ---------- ③ 营业时间为空 ----------
def test_03_empty_hours_not_dropped_by_open_now_filter(dirty):
    vid, f = dirty["vid"], dirty["floors"]["门诊楼3层"]
    pid = _poi(vid, f, "无营业时间商铺", hours=None)
    r = httpx.get(f"{BASE}/pois", params={"venue_id": vid, "open_now": "true"})
    assert r.status_code == 200
    ids = [i["id"] for i in r.json()["items"]]
    assert pid in ids, "空营业时间不得因 open_now 过滤而消失（应视为未知而非关闭）"


# ---------- ④ 超长介绍 ----------
def test_04_very_long_intro(dirty):
    vid, f = dirty["vid"], dirty["floors"]["门诊楼3层"]
    pid = _poi(vid, f, "超长介绍商铺", intro="长" * 5000)
    r = httpx.get(f"{BASE}/pois/{pid}", params={"venue_id": vid})
    assert r.status_code == 200
    assert len(r.json()["intro"]) == 5000, "超长介绍应完整存取（切片在 RAG 层）"


# ---------- ⑤ 坐标越界 ----------
def test_05_out_of_bounds_coords_plan_2003(dirty):
    f = dirty["floors"]["门诊楼3层"]
    n1 = _node(dirty["vid"], f, 600, 400)
    _poi(dirty["vid"], f, "越界商铺", x=-500, y=99999)
    n2 = _node(dirty["vid"], f, -500, 99999)
    _edge(n1, n2)
    body = _plan(n1, n2)
    assert body.get("error_code") in (2003, None), \
        f"越界坐标期望 2003 或可达，实为 {body}"


# ---------- ⑥ 某层无垂直交通 ----------
def test_06_floor_without_vertical_transport(dirty):
    f3, f2 = dirty["floors"]["门诊楼3层"], dirty["floors"]["急诊2层"]
    n1 = _node(dirty["vid"], f3, 300, 300)
    n2 = _node(dirty["vid"], f3, 400, 300)
    _edge(n1, n2)
    n3 = _node(dirty["vid"], f2, 300, 300)
    body = _plan(n1, n3)
    assert body.get("error_code") == 2003, \
        f"无垂直交通跨层必须 2003，实为 {body}"


# ---------- ⑦ 孤岛节点 ----------
def test_07_island_node_plan_2003(dirty):
    f = dirty["floors"]["门诊楼3层"]
    n1 = _node(dirty["vid"], f, 600, 400)
    n2 = _node(dirty["vid"], f, 700, 400)
    _edge(n1, n2)
    island = _node(dirty["vid"], f, 900, 900)  # 孤岛：无边
    from spatial_model import connected_components

    comps = connected_components([(n, 0, 0) for n in (n1, n2, island)], [(n1, n2)])
    assert sorted(len(c) for c in comps) == [1, 2], "M2 连通分量应检出孤岛"
    body = _plan(n1, island)
    assert body.get("error_code") == 2003, f"孤岛期望 2003，实为 {body}"


# ---------- ⑧ 库存为 0 与并发不超发 ----------
def test_08_zero_stock_and_no_oversell(dirty):
    vid = dirty["vid"]
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute(
            "insert into coupons (tenant_id, venue_id, title, coupon_type, threshold, "
            "value, total_qty, claimed_qty, start_at, end_at, status) "
            "values ((select id from tenants where code='shanqueli-demo'), %s, "
            "'零库存体检券', 'full_reduction', 0, 10, 500, 500, "
            "now() - interval '1 day', now() + interval '1 day', 'active') returning id",
            (vid,))
        zero_id = cur.fetchone()[0]
        cur.execute(
            "insert into coupons (tenant_id, venue_id, title, coupon_type, threshold, "
            "value, total_qty, claimed_qty, start_at, end_at, status) "
            "values ((select id from tenants where code='shanqueli-demo'), %s, "
            "'单张体检券', 'full_reduction', 0, 10, 1, 0, "
            "now() - interval '1 day', now() + interval '1 day', 'active') returning id",
            (vid,))
        one_id = cur.fetchone()[0]
        conn.commit()
    r = httpx.post(f"{BASE}/coupons/{zero_id}/claim",
                   json={"anonymous_id": "dirty-01"})
    assert r.status_code == 200 and r.json().get("error_code") == 4002, r.text

    import concurrent.futures

    def claim(i):
        return httpx.post(f"{BASE}/coupons/{one_id}/claim",
                          json={"anonymous_id": f"dirty-conc-{i}"}).json()

    with concurrent.futures.ThreadPoolExecutor(8) as ex:
        results = list(ex.map(claim, range(8)))
    won = [r for r in results if r.get("id") and not r.get("duplicate")]
    dups = [r for r in results if r.get("duplicate")]
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute("select claimed_qty from coupons where id=%s", (one_id,))
        qty = cur.fetchone()[0]
    assert qty == 1, f"并发领取不得超发，claimed_qty={qty}"
    assert len(won) == 1, f"恰好一人得券，实为 {len(won)}"
    assert all(r.get("duplicate") or r.get("error_code") == 4002
               for r in results if r.get("id") is None or r.get("duplicate")), \
        "其余请求只能是重放或售罄"


# ---------- ⑨ 特殊字符 ----------
def test_09_special_chars_safe(dirty):
    vid, f = dirty["vid"], dirty["floors"]["门诊楼3层"]
    weird = '<script>alert(1)</script>🙄"引号\反斜杠'
    pid = _poi(vid, f, weird)
    r = httpx.get(f"{BASE}/pois/{pid}", params={"venue_id": vid})
    assert r.status_code == 200
    assert r.json()["name"] == weird, "特殊字符应原样存储（渲染转义是前端职责）"
    r2 = httpx.get(f"{BASE}/pois", params={"venue_id": vid, "keyword": "<script>"})
    assert r2.status_code == 200, "特殊字符关键词搜索不得 500"


# ---------- ⑩ 非标准楼层名 ----------
def test_10_nonstandard_floor_names(dirty):
    f3, fb = dirty["floors"]["门诊楼3层"], dirty["floors"]["住院部B区"]
    n1 = _node(dirty["vid"], f3, 500, 300)
    n2 = _node(dirty["vid"], fb, 500, 400)
    # 门诊楼3层(level3) → 住院部B区(level-2)：经电梯节点人工连边模拟垂直交通
    elev3, elevb = _node(dirty["vid"], f3, 600, 400), _node(dirty["vid"], fb, 600, 400)
    _edge(n1, elev3, 20.0)
    _edge(elev3, elevb, 5.0)
    _edge(elevb, n2, 20.0)
    body = _plan(n1, n2)
    assert "error_code" not in body, \
        f"非标准楼层名跨层必须可规划（level 数值驱动），实为 {body}"
    assert body["total_distance_meter"] > 0


# ---------- ⑪ 图片 URL 失效 ----------
def test_11_broken_image_urls_passthrough(dirty):
    vid, f = dirty["vid"], dirty["floors"]["门诊楼3层"]
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute(
            "insert into pois (tenant_id, venue_id, floor_id, category_code, name, status, "
            "position_x, position_y, images) values ((select id from tenants "
            "where code='shanqueli-demo'), %s, %s, 'retail', '失效图商铺', 'published', "
            "500, 300, "
            "'[{\"url\": \"https://invalid.example/404.jpg\", \"sort\": 1}]'::jsonb) "
            "returning id", (vid, f))
        pid = cur.fetchone()[0]
        conn.commit()
    r = httpx.get(f"{BASE}/pois/{pid}", params={"venue_id": vid})
    assert r.status_code == 200
    assert r.json()["images"][0]["url"].startswith("https://invalid"), \
        "后端原样透传，占位图由前端渲染（行为约定）"


# ---------- ⑫ 5000 条导入 ----------
def test_12_bulk_5000_pois(dirty):
    import time

    vid, f = dirty["vid"], dirty["floors"]["门诊楼3层"]
    t0 = time.monotonic()
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        args = [(vid, f, f"bulk-{i:05d}", 500 + (i % 200), 400 + (i % 200))
                for i in range(5000)]
        cur.executemany(
            "insert into pois (tenant_id, venue_id, floor_id, category_code, name, "
            "status, position_x, position_y) values ((select id from tenants "
            "where code='shanqueli-demo'), %s, %s, 'retail', %s, 'published', %s, %s)",
            args)
        conn.commit()
    elapsed = time.monotonic() - t0
    r = httpx.get(f"{BASE}/pois", params={"venue_id": vid, "keyword": "bulk-",
                                          "page_size": 100})
    assert r.status_code == 200 and r.json()["total"] >= 5000
    assert elapsed < 30, f"5000 条写入 {elapsed:.1f}s 超时（应分批/<30s）"
