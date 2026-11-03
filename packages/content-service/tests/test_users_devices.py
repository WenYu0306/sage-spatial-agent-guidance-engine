"""M8 B4 验收：设备列表（PRD 7.4）与账号管理（PRD 2.2 账号与角色管理）。"""

from __future__ import annotations


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_devices_list_admin_only(client, tokens):
    r = client.get("/api/v1/devices", headers=_h(tokens["rbac_admin"]))
    body = r.json()
    assert r.status_code == 200 and body["items"], "seed 有 screen-f1-01"
    dev = body["items"][0]
    assert {"code", "name", "device_type", "status"} <= set(dev)
    denied = client.get("/api/v1/devices", headers=_h(tokens["rbac_editor"]))
    assert denied.status_code == 403 and denied.json()["error_code"] == 1003, \
        "PRD 2.2：设备管理 editor 无权限"


def test_users_list_and_create_editor(client, tokens, accounts, dsn):
    import psycopg

    h = _h(tokens["rbac_admin"])
    r = client.get("/api/v1/users", headers=h)
    assert r.status_code == 200
    users = r.json()["items"]
    assert any(u["username"] == "rbac_admin" for u in users), "列表含角色明细"
    created = client.post("/api/v1/users", headers=h, json={
        "username": "rbac_new_editor", "display_name": "新编辑",
        "role": "venue_editor", "password": "new-pass-123"})
    assert created.status_code == 200, created.text
    uid = created.json()["id"]
    try:
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "select r.code from user_roles ur join roles r on r.id=ur.role_id "
                "where ur.user_id=%s", (uid,))
            assert cur.fetchone()[0] == "venue_editor"
        # editor 不能管账号（PRD 2.2 账号与角色管理：editor 无）
        denied = client.get("/api/v1/users", headers=_h(tokens["rbac_editor"]))
        assert denied.status_code == 403 and denied.json()["error_code"] == 1003
        # 新账号可登录（口令哈希正确）
        login = client.post("/api/v1/auth/login", json={
            "tenant_code": "shanqueli-demo", "username": "rbac_new_editor",
            "password": "new-pass-123"})
        assert login.status_code == 200 and login.json()["roles"] == ["venue_editor"]
    finally:
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute("delete from users where id=%s", (uid,))
            conn.commit()


def test_merchant_cannot_manage_accounts(client, tokens):
    r = client.post("/api/v1/users", headers=_h(tokens["rbac_merchant"]),
                    json={"username": "x", "display_name": "x", "role": "venue_editor",
                          "password": "x-pass-123"})
    assert r.status_code == 403 and r.json()["error_code"] == 1003


def test_disable_user_via_patch(client, tokens, accounts, dsn):
    import psycopg

    h = _h(tokens["rbac_admin"])
    uid = accounts["users"]["rbac_editor"]
    r = client.patch(f"/api/v1/users/{uid}", headers=h, json={"status": "disabled"})
    assert r.status_code == 200 and r.json()["status"] == "disabled"
    try:
        login = client.post("/api/v1/auth/login", json={
            "tenant_code": "shanqueli-demo", "username": "rbac_editor",
            "password": accounts["password"]})
        assert login.status_code == 401, "禁用账号不能登录"
    finally:
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute("update users set status='active' where id=%s", (uid,))
            conn.commit()
