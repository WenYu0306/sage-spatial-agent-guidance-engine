"""M1 RBAC API 验收：PRD 2.3 五条越权用例全部自动化 + 登录/刷新/锁定流。

受保护端点用代表性 stub（账号管理/场地数据查询/门店写/内容写）——
M8 内容服务建成后由真业务端点复用同一套依赖。越权一律 403/1003、
无凭证 401/1001，且 403 写 operation_logs（PRD 2.2/10）。
"""

from __future__ import annotations

import psycopg
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from platform_core.auth import TokenSubject, issue_tokens
from platform_core.auth_router import (
    AuthRuntime,
    create_auth_router,
    install_error_handlers,
)

TENANT = "shanqueli-demo"
PASSWORD = "demo-pass-123"


@pytest.fixture(scope="module")
def runtime(dsn):
    return AuthRuntime(dsn=dsn)


@pytest.fixture(scope="module")
def accounts(dsn):
    """自建 rbac_* 测试账号（不碰 seed 演示账号：改共享数据会污染其他测试）。

    角色/范围与 PRD 2.2 矩阵一致：venue_admin/venue_editor 绑本场地，
    merchant 绑定门店野莓茶集。模块结束级联清理。
    """
    from platform_core.auth import hash_password

    spec = (("rbac_admin", "venue_admin", None),
            ("rbac_editor", "venue_editor", None),
            ("rbac_merchant", "merchant", "STORE"))
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("select id from tenants where code=%s", (TENANT,))
        tid = cur.fetchone()[0]
        cur.execute("select id from venues where tenant_id=%s limit 1", (tid,))
        vid = cur.fetchone()[0]
        cur.execute("select id from pois where tenant_id=%s and name='野莓茶集'", (tid,))
        store_poi = cur.fetchone()[0]
        users = {}
        hashed = hash_password(PASSWORD)
        for username, role, store in spec:
            cur.execute("delete from users where tenant_id=%s and username=%s",
                        (tid, username))
            cur.execute(
                "insert into users (tenant_id, username, password_hash, display_name) "
                "values (%s, %s, %s, 'rbac-test') returning id", (tid, username, hashed))
            uid = cur.fetchone()[0]
            cur.execute(
                "insert into user_roles (user_id, role_id, venue_id, merchant_id) "
                "values (%s, (select id from roles where code=%s), %s, %s)",
                (uid, role, vid, store_poi if store == "STORE" else None))
            users[username] = uid
        conn.commit()
    yield {"tid": tid, "vid": vid, "users": users, "store_poi": store_poi}
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        for username, _, _ in spec:
            cur.execute("delete from users where tenant_id=%s and username=%s",
                        (tid, username))
        conn.commit()


@pytest.fixture(scope="module")
def client(runtime, accounts):
    app = FastAPI()
    app.include_router(create_auth_router(runtime))
    install_error_handlers(app)

    @app.get("/api/v1/admin/accounts")
    def admin_accounts(ctx=Depends(runtime.dependency("platform_admin", "venue_admin"))):
        return {"ok": True, "tenant_id": ctx.tenant_id}

    @app.get("/api/v1/demo/pois/{venue_id}")
    def venue_pois(venue_id: int, ctx=Depends(runtime.dependency("venue_admin", "venue_editor"))):
        ctx.ensure_venue(venue_id)  # PRD 2.3 案例 2：URL 改场地 ID 必须拦
        return {"ok": True, "venue_id": ctx.venue_id}

    @app.post("/api/v1/demo/stores/{poi_id}")
    def store_write(poi_id: int, ctx=Depends(runtime.dependency("merchant"))):
        ctx.ensure_merchant(poi_id)  # PRD 2.3 案例 3：改别家门店必须拦
        return {"ok": True}

    @app.post("/api/v1/demo/content")
    def content_write(ctx=Depends(
            runtime.dependency("venue_admin", "venue_editor", "platform_admin"))):
        return {"ok": True}

    @app.post("/api/v1/demo/heartbeat")
    def heartbeat(ctx=Depends(runtime.dependency("device"))):
        return {"ok": True, "device_id": ctx.device_id}

    return TestClient(app, raise_server_exceptions=False)


def _login(client, username, password=PASSWORD, tenant=TENANT):
    return client.post("/api/v1/auth/login",
                       json={"tenant_code": tenant, "username": username,
                             "password": password})


def test_login_success_and_profile(client):
    r = _login(client, "rbac_admin")
    body = r.json()
    assert r.status_code == 200 and body["access_token"] and body["refresh_token"]
    assert body["roles"] == ["venue_admin"] and body["venue_id"]


def test_login_wrong_password_is_401_1001(client):
    """防用户枚举：未知账号与错口令必须同状态码同话术（PRD 9）。"""
    r = _login(client, "demo_admin", password="nope")
    assert r.status_code == 401 and r.json()["error_code"] == 1001
    ghost = _login(client, "no_such_user", password="nope")
    assert ghost.status_code == 401
    assert ghost.json()["message"] == r.json()["message"]


def test_refresh_rotates_tokens(client):
    tokens = _login(client, "rbac_editor").json()
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    body = r.json()
    assert r.status_code == 200 and body["access_token"]
    assert body["roles"] == ["venue_editor"], "刷新后按库重查角色"


def test_refresh_with_access_token_rejected(client):
    tokens = _login(client, "rbac_editor").json()
    r = client.post("/api/v1/auth/refresh",
                    json={"refresh_token": tokens["access_token"]})
    assert r.json().get("error_code") == 1001


# ---------- PRD 2.3 越权五连 ----------

def test_case1_editor_cannot_touch_accounts(client, accounts):
    token = _login(client, "rbac_editor").json()["access_token"]
    r = client.get("/api/v1/admin/accounts",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403 and r.json()["error_code"] == 1003


def test_case2_cross_venue_query_blocked(client, accounts):
    token = _login(client, "rbac_admin").json()["access_token"]
    other_venue = accounts["vid"] + 99999
    r = client.get(f"/api/v1/demo/pois/{other_venue}",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403 and r.json()["error_code"] == 1003
    ok = client.get(f"/api/v1/demo/pois/{accounts['vid']}",
                    headers={"Authorization": f"Bearer {token}"})
    assert ok.status_code == 200, "本场地访问应放行"


def test_case3_merchant_cannot_write_other_store(client, accounts):
    token = _login(client, "rbac_merchant").json()["access_token"]
    r = client.post(f"/api/v1/demo/stores/{accounts['store_poi'] + 1}",
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403 and r.json()["error_code"] == 1003
    ok = client.post(f"/api/v1/demo/stores/{accounts['store_poi']}",
                     headers={"Authorization": f"Bearer {token}"})
    assert ok.status_code == 200


def test_case4_guest_without_token_gets_401(client):
    r = client.get("/api/v1/admin/accounts")
    assert r.status_code == 401 and r.json()["error_code"] == 1001


def test_case5_device_token_cannot_write_content(client, accounts):
    subject = TokenSubject(user_id=1, tenant_id=accounts["tid"], roles=["device"],
                           venue_id=accounts["vid"], device_id=1)
    token = issue_tokens(subject)["access_token"]
    r = client.post("/api/v1/demo/content",
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403 and r.json()["error_code"] == 1003
    hb = client.post("/api/v1/demo/heartbeat",
                     headers={"Authorization": f"Bearer {token}"})
    assert hb.status_code == 200, "设备只能上报心跳"


def test_403_writes_operation_log(client, accounts, dsn):
    token = _login(client, "rbac_editor").json()["access_token"]
    client.get("/api/v1/admin/accounts",
               headers={"Authorization": f"Bearer {token}",
                        "X-Trace-Id": "tr_oplog_test"})
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "select action, trace_id from operation_logs "
            "where trace_id='tr_oplog_test' order by id desc limit 1")
        row = cur.fetchone()
    assert row and row[0] == "access_denied" and row[1] == "tr_oplog_test"


def test_lockout_blocks_login_then_recovers(client, runtime, accounts, dsn):
    for _ in range(runtime.policy.max_attempts):
        _login(client, "rbac_merchant", password="bad")
    r = _login(client, "rbac_merchant")  # 正确口令也应被锁
    assert r.json().get("error_code") == 1001
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("update users set failed_logins=0, locked_until=NULL "
                    "where tenant_id=%s and username='rbac_merchant'",
                    (accounts["tid"],))
        conn.commit()
    assert _login(client, "rbac_merchant").status_code == 200


def _guest_client(runtime) -> TestClient:
    """本地构建含 guest 路由的应用（夹具 client 不含 demo 路由）。"""
    app = FastAPI()
    app.include_router(create_auth_router(runtime))
    install_error_handlers(app)

    @app.get("/api/v1/demo/guest-pois")
    def guest_pois(ctx=Depends(runtime.optional())):
        return {"tenant_id": ctx.tenant_id, "venue_id": ctx.venue_id, "roles": ctx.roles}

    return TestClient(app)


def test_optional_dependency_guest_with_venue_id(client, runtime, accounts):
    """guest 依赖：无 token + ?venue_id= → 匿名身份（租户自场地反查，PRD 595 guest 除外）。"""
    c = _guest_client(runtime)
    r = c.get("/api/v1/demo/guest-pois", params={"venue_id": accounts["vid"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tenant_id"] == accounts["tid"] and body["venue_id"] == accounts["vid"]
    assert body["roles"] == ["guest"]


def test_optional_dependency_requires_valid_venue(client, runtime):
    c = _guest_client(runtime)
    assert c.get("/api/v1/demo/guest-pois",
                 params={"venue_id": 999999}).status_code == 401
    assert c.get("/api/v1/demo/guest-pois").status_code == 401


def test_optional_dependency_with_token_still_works(client, runtime, accounts):
    c = _guest_client(runtime)
    subject = TokenSubject(user_id=1, tenant_id=accounts["tid"], roles=["venue_admin"],
                           venue_id=accounts["vid"])
    token = issue_tokens(subject)["access_token"]
    r = c.get("/api/v1/demo/guest-pois",
              headers={"Authorization": f"Bearer {token}"},
              params={"venue_id": accounts["vid"]})
    assert r.status_code == 200 and "venue_admin" in r.json()["roles"]
