"""M8 B3 验收：活动状态机、领券幂等与售罄、知识文档 CRUD。"""

from __future__ import annotations

import datetime as dt

import psycopg
import pytest


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _dsn():
    import os

    return os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)


ACT = {"act_type": "shop_promo", "title": "测试活动", "description": "测试",
       "start_at": (dt.datetime.now() - dt.timedelta(hours=1)).isoformat(),
       "end_at": (dt.datetime.now() + dt.timedelta(days=1)).isoformat()}


@pytest.fixture()
def cleanup_pois(dsn):
    made = []

    def add(pid):
        made.append(pid)

    yield add
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        for pid in made:
            cur.execute("delete from activities where poi_id=%s", (pid,))
            cur.execute("delete from pois where id=%s", (pid,))
        conn.commit()


def _mk_activity(client, tokens, accounts, **over):
    body = {**ACT, "venue_id": accounts["vid"], **over}
    r = client.post("/api/v1/activities", headers=_h(tokens["rbac_editor"]), json=body)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _cleanup_acts(dsn, ids):
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        for aid in ids:
            cur.execute("delete from activities where id=%s", (aid,))
        conn.commit()


def test_activity_state_machine(client, tokens, accounts, dsn):
    aid = _mk_activity(client, tokens, accounts)
    try:
        h = _h(tokens["rbac_admin"])
        assert client.post(f"/api/v1/activities/{aid}/publish",
                           headers=h, json={"target": "active"}).status_code == 409
        assert client.post(f"/api/v1/activities/{aid}/publish",
                           headers=h, json={"target": "pending"}).json()["status"] == "pending"
        assert client.post(f"/api/v1/activities/{aid}/publish",
                           headers=h, json={"target": "active"}).json()["status"] == "active"
        assert client.post(f"/api/v1/activities/{aid}/publish",
                           headers=h, json={"target": "ended"}).json()["status"] == "ended"
        assert client.post(f"/api/v1/activities/{aid}/publish",
                           headers=h, json={"target": "archived"}).json()["status"] == "archived"
    finally:
        _cleanup_acts(dsn, [aid])


def test_editor_cannot_activate(client, tokens, accounts, dsn):
    aid = _mk_activity(client, tokens, accounts)
    try:
        client.post(f"/api/v1/activities/{aid}/publish",
                    headers=_h(tokens["rbac_editor"]), json={"target": "pending"})
        r = client.post(f"/api/v1/activities/{aid}/publish",
                        headers=_h(tokens["rbac_editor"]), json={"target": "active"})
        assert r.status_code == 403 and r.json()["error_code"] == 1003
    finally:
        _cleanup_acts(dsn, [aid])


def test_activities_list_filters_status(client, tokens, accounts, dsn):
    aid = _mk_activity(client, tokens, accounts, title="状态过滤活动")
    try:
        items = client.get("/api/v1/activities", headers=_h(tokens["rbac_admin"]),
                           params={"status": "draft", "title": "状态过滤活动"}
                           ).json()["items"]
        assert [i["id"] for i in items] == [aid]
    finally:
        _cleanup_acts(dsn, [aid])


# ---------- 领券 ----------

@pytest.fixture()
def coupon(dsn, accounts):
    """新建测试券：总量 2，关联野莓茶集（merchant 门店）。"""
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "insert into coupons (tenant_id, venue_id, poi_id, title, coupon_type, "
            "threshold, value, total_qty, claimed_qty, per_user_limit, start_at, "
            "end_at, status) values (%s, %s, %s, '测试券', 'full_reduction', 50, 20, "
            "2, 0, 1, now() - interval '1 hour', now() + interval '1 day', 'active') "
            "returning id", (accounts["tid"], accounts["vid"], accounts["store_poi"]))
        cid = cur.fetchone()[0]
        conn.commit()
    yield cid
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("delete from coupon_claims where coupon_id=%s", (cid,))
        cur.execute("delete from coupons where id=%s", (cid,))
        conn.commit()


def test_claim_idempotent_same_anonymous(client, tokens, coupon, dsn):
    body = {"anonymous_id": "guest-abc"}
    r1 = client.post(f"/api/v1/coupons/{coupon}/claim", json=body)
    r2 = client.post(f"/api/v1/coupons/{coupon}/claim", json=body)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json().get("duplicate") is not True, "首次领取"
    assert r2.json().get("duplicate") is True, "幂等重放返回既有券（4003 语义容忍）"
    with psycopg.connect(_dsn()) as conn, conn.cursor() as cur:
        cur.execute("select claimed_qty from coupons where id=%s", (coupon,))
        assert cur.fetchone()[0] == 1, "重放不得重复扣库存"


def test_claim_different_anonymous_consumes_stock(client, coupon):
    a = client.post(f"/api/v1/coupons/{coupon}/claim", json={"anonymous_id": "g1"})
    b = client.post(f"/api/v1/coupons/{coupon}/claim", json={"anonymous_id": "g2"})
    assert a.status_code == 200 and b.status_code == 200


def test_claim_sold_out_4002(client, coupon):
    client.post(f"/api/v1/coupons/{coupon}/claim", json={"anonymous_id": "g1"})
    client.post(f"/api/v1/coupons/{coupon}/claim", json={"anonymous_id": "g2"})
    r = client.post(f"/api/v1/coupons/{coupon}/claim", json={"anonymous_id": "g3"})
    assert r.status_code == 200 and r.json()["error_code"] == 4002, "售罄（库存原子判定）"


def test_claim_requires_anonymous_id(client, coupon):
    r = client.post(f"/api/v1/coupons/{coupon}/claim", json={})
    assert r.status_code == 422


def test_coupons_list_shows_remaining(client, tokens, coupon):
    items = client.get("/api/v1/coupons", headers=_h(tokens["rbac_admin"])).json()["items"]
    row = [i for i in items if i["id"] == coupon][0]
    assert row["remaining"] == 2


# ---------- 知识文档 ----------

DOC = {"doc_type": "faq", "title": "测试知识文档", "content": "会员积分如何使用？"}


def test_knowledge_doc_crud_and_version_bump(client, tokens, accounts, dsn):
    h = _h(tokens["rbac_editor"])
    r = client.post("/api/v1/knowledge-documents", headers=h,
                    json={**DOC, "venue_id": accounts["vid"]})
    assert r.status_code == 200, r.text
    did = r.json()["id"]
    try:
        r2 = client.patch(f"/api/v1/knowledge-documents/{did}", headers=h,
                          json={"content": "积分可在服务台兑换"})
        assert r2.json()["version"] == 2, "内容更新版本号自增"
        listing = client.get("/api/v1/knowledge-documents", headers=h,
                             params={"title": "测试知识文档"}).json()["items"]
        assert [i["id"] for i in listing] == [did]
        # merchant 无权管理知识内容（PRD 2.2 矩阵）
        denied = client.post("/api/v1/knowledge-documents",
                             headers=_h(tokens["rbac_merchant"]),
                             json={**DOC, "venue_id": accounts["vid"]})
        assert denied.status_code == 403 and denied.json()["error_code"] == 1003
    finally:
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute("delete from knowledge_documents where id=%s", (did,))
            conn.commit()


def test_merchant_cannot_create_activity_for_others(client, tokens, accounts, dsn):
    """merchant 创建活动必须绑定自己门店。"""
    r = client.post("/api/v1/activities", headers=_h(tokens["rbac_merchant"]),
                    json={**ACT, "venue_id": accounts["vid"], "poi_id": None})
    assert r.status_code == 403, r.text  # 无门店归属的商场级活动 merchant 不可建
