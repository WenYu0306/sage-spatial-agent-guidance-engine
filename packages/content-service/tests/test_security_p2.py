"""P2 安全批（审计 S-1~S-5）：提权拦截/商户归属/心跳绑定/claim 限流。"""

from __future__ import annotations

import psycopg

PASSWORD = "rbac-pass-123"


def _mk_activity(client, token, poi_id, title):
    import datetime as dt

    r = client.post("/api/v1/activities", headers={"Authorization": f"Bearer {token}"},
                    json={"venue_id": 1, "poi_id": poi_id, "act_type": "promo",
                          "title": title, "description": "P2 测试",
                          "start_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                          "end_at": (dt.datetime.now(dt.timezone.utc)
                                     + dt.timedelta(days=1)).isoformat()})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_user_create_cannot_escalate_to_platform_admin(client, tokens, dsn):
    """venue_admin 不得创建 platform_admin（审计 S-3 提权）。"""
    import psycopg

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("delete from user_roles where user_id in "
                    "(select id from users where username='evil_pa')")
        cur.execute("delete from users where username='evil_pa'")
        conn.commit()
    r = client.post("/api/v1/users", headers={"Authorization": f"Bearer {tokens['rbac_admin']}"},
                    json={"username": "evil_pa", "display_name": "x", "role": "platform_admin",
                          "password": "password-123"})
    assert r.status_code == 403, r.text


def test_user_create_merchant_requires_store(client, tokens, dsn):
    """merchant 建号必须绑门店（审计 S-3：无绑定 merchant 等于空壳越权面）。"""
    body = {"username": "rbac_merchant_p2", "display_name": "x", "role": "merchant",
            "password": PASSWORD}
    r = client.post("/api/v1/users", headers={"Authorization": f"Bearer {tokens['rbac_admin']}"},
                    json=body)
    assert r.status_code == 403, r.text
    body["store"] = "野莓茶集"
    r2 = client.post("/api/v1/users", headers={"Authorization": f"Bearer {tokens['rbac_admin']}"},
                     json=body)
    assert r2.status_code == 200, r2.text
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "select ur.merchant_id from users u join user_roles ur on ur.user_id=u.id "
            "where u.username='rbac_merchant_p2'")
        mid = cur.fetchone()[0]
        assert mid is not None, "merchant 绑定必须落库"
        cur.execute("delete from user_roles where user_id in "
                    "(select id from users where username='rbac_merchant_p2')")
        cur.execute("delete from users where username='rbac_merchant_p2'")
        conn.commit()


def test_merchant_cannot_patch_other_merchant_activity(client, tokens, accounts, dsn):
    """商户 A 不得改商户 B 的活动（审计 S-4 归属校验）。"""

    # 灶门炭火锅 = 另一商户锚点门店（非野莓茶集）
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("select id from pois where name='灶门炭火锅'")
        other_poi = cur.fetchone()[0]
        conn.commit()
    aid = _mk_activity(client, tokens["rbac_admin"], other_poi, "P2 跨商户活动")
    try:
        r = client.patch(f"/api/v1/activities/{aid}",
                         headers={"Authorization": f"Bearer {tokens['rbac_merchant']}"},
                         json={"description": "商户 A 篡改"})
        assert r.status_code == 403, r.text
        r2 = client.post(f"/api/v1/activities/{aid}/publish",
                         headers={"Authorization": f"Bearer {tokens['rbac_merchant']}"},
                         json={"target": "published"})
        assert r2.status_code == 403, r2.text
        # 场地角色不受限
        r3 = client.patch(f"/api/v1/activities/{aid}",
                          headers={"Authorization": f"Bearer {tokens['rbac_admin']}"},
                          json={"description": "场地管理员改"})
        assert r3.status_code == 200, r3.text
    finally:
        # POST /activities 是创建不是 upsert：不清理会跨运行累积（曾泄漏 14 行）
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute("delete from activities where title='P2 跨商户活动'")
            conn.commit()


def test_claim_rate_limited(client, tokens, dsn):
    """领券限流：同 anonymous_id 高频 → 429/9002（审计 S-5）。"""
    last = None
    for i in range(40):
        last = client.post(
            "/api/v1/coupons/1/claim",
            json={"anonymous_id": f"p2-ratelimit-{i:02d}"})
    assert last.status_code == 429 and last.json()["error_code"] == 9002
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("delete from coupon_claims where anonymous_id like 'p2-ratelimit-%'")
        conn.commit()
