"""M2 服务化（挂 M8）：设施最近查询 / 路网读写 / pois 出参扩展与场景参数。"""

from __future__ import annotations

import psycopg


def test_pois_nearest_same_floor_first(client, tokens, accounts, dsn):
    """设施最近查询：有位置时同层优先+距离升序；无位置按热度（M5 facility.nearest 迁移目标）。"""
    h = {"Authorization": f"Bearer {tokens['rbac_admin']}"}
    # F1 卫生间 (730,410)，position 给 F1 中庭 (600,400)
    r = client.get("/api/v1/pois/nearest", headers=h,
                   params={"venue_id": accounts["vid"], "category_code": "toilet",
                           "x": 600, "y": 400, "floor_id": _fid(dsn, "F1"), "limit": 3})
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert items and items[0]["name"] == "F1 卫生间", items[:2]
    assert items[0]["same_floor"] is True
    # 无位置：按热度，不声称同层
    r2 = client.get("/api/v1/pois/nearest", headers=h,
                    params={"venue_id": accounts["vid"], "category_code": "toilet", "limit": 3})
    assert r2.status_code == 200
    assert all(i["same_floor"] is False for i in r2.json()["items"])
    assert r2.json()["items"][0]["hot_score"] >= r2.json()["items"][-1]["hot_score"]


def test_pois_nearest_guest_and_published_only(client, dsn):
    """guest 可用（optional）；草稿不出现。"""

    from platform_core.events import new_event_id

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "insert into pois (tenant_id, venue_id, floor_id, category_code, name, status, "
            "position_x, position_y) values (1, 1, (select min(id) from floors where venue_id=1), "
            "'toilet', %s, 'draft', 700, 400) returning id",
            (f"草稿厕所{new_event_id()[:6]}",))
        conn.commit()
    try:
        r = client.get("/api/v1/pois/nearest",
                       params={"venue_id": 1, "category_code": "toilet", "limit": 20})
        assert r.status_code == 200, r.text
        assert not any(i["name"].startswith("草稿厕所") for i in r.json()["items"])
    finally:
        # 失败路径也清理（13.3 铁律：测试数据泄漏会连锁炸 seed 行数断言）
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute("delete from pois where name like '草稿厕所%'")
            conn.commit()


def test_pois_scene_tag_bidirectional(client):
    """场景参数迁移（行为一致回归）：'家庭聚餐' 命中 tag[聚餐]。"""
    r = client.get("/api/v1/pois", params={"venue_id": 1, "category_code": "restaurant",
                                           "scene_tag": "家庭聚餐"})
    assert r.status_code == 200, r.text
    names = [i["name"] for i in r.json()["items"]]
    assert "云雀灶火锅" in names, names
    # 出参扩展：tags/hot_score/position/楼层名
    first = r.json()["items"][0]
    assert {"tags", "hot_score", "position_x", "position_y", "floor"} <= set(first)


def test_route_nodes_read_and_write(client, tokens, accounts, dsn):
    """路网读写 API（PRD 7.3）：venue_admin 可读写；按 poi_id 过滤供 M5 目标解析。"""
    h = {"Authorization": f"Bearer {tokens['rbac_admin']}"}
    vid = accounts["vid"]
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("select id from pois where name='云雀灶火锅'")
        pid = cur.fetchone()[0]
    r = client.post("/api/v1/route-nodes", headers=h,
                    json={"venue_id": vid, "floor_id": _fid(dsn, "F1"), "node_type": "waypoint",
                          "x": 999, "y": 888, "accessible": True})
    assert r.status_code == 200, r.text
    nid = r.json()["id"]
    try:
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute("update route_nodes set poi_id=%s where id=%s", (pid, nid))
            conn.commit()
        # 按 poi_id 过滤读（M5 goal 解析契约）+ guest 可读（M5 服务间调用走 optional）
        for headers in (h, {}):
            r2 = client.get("/api/v1/route-nodes", headers=headers,
                            params={"venue_id": vid, "poi_id": pid})
            assert r2.status_code == 200, r2.text
            assert any(n["id"] == nid for n in r2.json()["items"])
        # merchant 不得写
        r4 = client.post("/api/v1/route-nodes",
                         headers={"Authorization": f"Bearer {tokens['rbac_merchant']}"},
                         json={"venue_id": vid, "floor_id": _fid(dsn, "F1"),
                               "node_type": "waypoint", "x": 1, "y": 1, "accessible": True})
        assert r4.status_code == 403
    finally:
        # 写测试残留会改变路网规模（route-engine 规模断言连锁失败）
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute("delete from route_nodes where id=%s", (nid,))
            conn.commit()


def _fid(dsn, name):
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("select id from floors where name=%s and venue_id=1", (name,))
        return cur.fetchone()[0]
