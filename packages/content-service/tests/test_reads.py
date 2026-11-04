"""M8 只读端点验收：auth 挂载、租户/场地范围注入、组合过滤与分页。"""

from __future__ import annotations


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}



def test_login_mounted_on_content_service(client, accounts):
    r = client.post("/api/v1/auth/login", json={
        "tenant_code": "shanqueli-demo", "username": "rbac_admin",
        "password": accounts["password"]})
    assert r.status_code == 200 and r.json()["access_token"]


def test_guest_without_token_gets_401(client):
    assert client.get("/api/v1/pois").status_code == 401


def test_venues_scoped_to_token_tenant(client, tokens):
    r = client.get("/api/v1/venues", headers=_h(tokens["rbac_admin"]))
    venues = r.json()["items"]
    assert venues and all(v["tenant_id"] for v in venues)


def test_floors_and_map_layer(client, tokens, accounts):
    vid = accounts["vid"]
    floors = client.get(f"/api/v1/venues/{vid}/floors",
                        headers=_h(tokens["rbac_editor"])).json()["items"]
    assert len(floors) == 3, "B1/F1/F2"
    layer = client.get(f"/api/v1/floors/{floors[0]['id']}/map-layer",
                       headers=_h(tokens["rbac_editor"])).json()
    assert layer["scale_meter"] and layer["width"]


def test_categories_list(client, tokens):
    r = client.get("/api/v1/categories", headers=_h(tokens["rbac_editor"]))
    assert r.json()["items"]


def test_pois_list_combined_filters_and_pagination(client, tokens, accounts):
    h = _h(tokens["rbac_admin"])
    r = client.get("/api/v1/pois", headers=h, params={"page": 1, "page_size": 10})
    body = r.json()
    assert body["total"] > 10 and len(body["items"]) == 10, "分页生效"
    r = client.get("/api/v1/pois", headers=h,
                   params={"keyword": "火锅", "page_size": 50})
    items = r.json()["items"]
    assert items and all("火锅" in i["name"] or "火锅" in (i.get("intro") or "")
                         for i in items)
    floor_ids = {i["floor_id"] for i in items}
    r = client.get("/api/v1/pois", headers=h,
                   params={"keyword": "火锅", "floor_id": min(floor_ids)})
    assert all(i["floor_id"] == min(floor_ids) for i in r.json()["items"])


def test_pois_open_now_filter(client, tokens, accounts, dsn):
    """回归：open_now 分支 SQL 与营业时段判定（临时全天时段 POI 必须命中）。"""
    import json as _json

    import psycopg

    h = _h(tokens["rbac_admin"])
    all_day = _json.dumps({d: ["00:00-23:59"] for d in
                           ("mon", "tue", "wed", "thu", "fri", "sat", "sun")})
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "insert into pois (tenant_id, venue_id, floor_id, category_code, name, "
            "position_x, position_y, business_hours, status) "
            "values (%s, %s, (select id from floors where venue_id=%s and level=1), "
            "'restaurant', '全天测试铺', 111, 222, %s, 'published') returning id",
            (accounts["tid"], accounts["vid"], accounts["vid"], all_day))
        pid = cur.fetchone()[0]
        conn.commit()
    try:
        body = client.get("/api/v1/pois", headers=h,
                          params={"open_now": "true", "page_size": 100}).json()
        assert pid in [i["id"] for i in body["items"]], "全天时段 POI 应命中 open_now"
    finally:
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute("delete from pois where id=%s", (pid,))
            conn.commit()


def test_poi_detail_includes_current_activities(client, tokens, accounts):
    with_pois = client.get("/api/v1/pois", headers=_h(tokens["rbac_admin"]),
                           params={"keyword": "火锅", "page_size": 1}).json()
    poi_id = with_pois["items"][0]["id"]
    detail = client.get(f"/api/v1/pois/{poi_id}",
                        headers=_h(tokens["rbac_admin"])).json()
    assert detail["id"] == poi_id and "activities" in detail and "coupons" in detail


def test_merchant_sees_store_scope_but_reads_all(client, tokens, accounts):
    """merchant 读列表不限定自己门店（PRD 7.3 读按权限），但查询参数只接受自己 merchant_id。"""
    r = client.get("/api/v1/pois", headers=_h(tokens["rbac_merchant"]),
                   params={"merchant_id": accounts["store_poi"]})
    assert r.json()["items"]


def test_guest_reads_published_only(client, accounts, dsn):
    """M12 guest 读端点（PRD 595 guest 除外）：无 token + ?venue_id= 可读，
    但只见 published POI 与在窗优惠；草稿不可见。"""
    tid, vid = accounts["tid"], accounts["vid"]
    # 直插一篇草稿 POI
    import psycopg

    from platform_core.events import new_event_id
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "insert into pois (tenant_id, venue_id, floor_id, category_code, name, "
            "status, position_x, position_y) values (%s, %s, "
            "(select min(id) from floors where venue_id=%s), 'retail', %s, "
            "'draft', 100, 100) returning id",
            (tid, vid, vid, f"草稿店{new_event_id()[:6]}",))
        draft_id = cur.fetchone()[0]
        conn.commit()
    r = client.get("/api/v1/pois", params={"venue_id": vid})
    assert r.status_code == 200, r.text
    names = [i["name"] for i in r.json()["items"]]
    assert not any(n.startswith("草稿店") for n in names), "guest 不得见草稿"
    assert r.json()["items"], "guest 应见到 published 店铺"
    # 草稿详情直取也拦
    assert client.get(f"/api/v1/pois/{draft_id}",
                      params={"venue_id": vid}).status_code == 403
    # 优惠在窗列表可读
    rc = client.get("/api/v1/coupons", params={"venue_id": vid})
    assert rc.status_code == 200 and "items" in rc.json()
    # 缺 venue_id 的 guest 请求 → 401
    assert client.get("/api/v1/pois").status_code == 401
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("delete from pois where id=%s", (draft_id,))
        conn.commit()
