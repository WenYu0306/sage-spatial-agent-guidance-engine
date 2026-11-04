"""M8 设备心跳（F-19/PRD 733）：device 角色专用，更新状态并打点 device_active。"""

from __future__ import annotations

import psycopg
import pytest

PASSWORD = "rbac-pass-123"


@pytest.fixture(scope="module")
def device_env(client, dsn, accounts):
    """设备角色账号 + 本场地/邻场地各一台设备（不碰 seed 演示设备）。"""
    from platform_core.auth import hash_password

    hashed = hash_password(PASSWORD)
    tid, vid = accounts["tid"], accounts["vid"]
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "select id from venues where tenant_id=%s and id<>%s order by id limit 1", (tid, vid))
        row = cur.fetchone()
        if row:
            other_vid = row[0]
        else:
            cur.execute(
                "insert into venues (tenant_id, name, venue_type, address, "
                "timezone, status) values (%s, 'rbac 隔离场地', 'mall', '测试', "
                "'Asia/Shanghai', 'active') returning id",
                (tid,))
            other_vid = cur.fetchone()[0]
        cur.execute("delete from users where tenant_id=%s and username='rbac_screen'", (tid,))
        cur.execute(
            "insert into users (tenant_id, username, password_hash, display_name) "
            "values (%s, 'rbac_screen', %s, 'rbac-screen') returning id", (tid, hashed))
        uid = cur.fetchone()[0]
        cur.execute(
            "insert into user_roles (user_id, role_id, venue_id) "
            "values (%s, (select id from roles where code='device'), %s)", (uid, vid))
        devs = {}
        for code, v in (("rbac_screen", vid), ("rbac-screen-b", other_vid)):
            cur.execute("delete from devices where tenant_id=%s and code=%s", (tid, code))
            cur.execute(
                "insert into devices (tenant_id, venue_id, code, name, device_type, status) "
                "values (%s, %s, %s, 'rbac 测试屏', 'screen', 'offline') returning id",
                (tid, v, code))
            devs[code] = cur.fetchone()[0]
        conn.commit()
    login = client.post("/api/v1/auth/login", json={
        "tenant_code": "shanqueli-demo", "username": "rbac_screen", "password": PASSWORD})
    assert login.status_code == 200, login.text
    yield {"token": login.json()["access_token"], "devs": devs,
           "accounts": accounts, "dsn": dsn}
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("delete from devices where tenant_id=%s and (code like %s or code like %s)",
                    (tid, "rbac_screen%", "rbac-screen-%"))
        cur.execute("delete from users where tenant_id=%s and username='rbac_screen'", (tid,))
        cur.execute("delete from venues where tenant_id=%s and name='rbac 隔离场地'", (tid,))
        conn.commit()


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_heartbeat_updates_and_emits_event(client, device_env):
    dev_id = device_env["devs"]["rbac_screen"]
    r = client.post(f"/api/v1/devices/{dev_id}/heartbeat",
                    headers=_h(device_env["token"]),
                    json={"status": "online", "app_version": "1.0.0-screen"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["device_id"] == dev_id
    with psycopg.connect(device_env["dsn"]) as conn, conn.cursor() as cur:
        cur.execute(
            "select status, app_version, last_seen_at is not null from devices where id=%s",
            (dev_id,))
        status, version, seen = cur.fetchone()
        assert (status, version, seen) == ("online", "1.0.0-screen", True)
        cur.execute(
            "select count(*) from events where event_type='device_active' and device_id=%s",
            (dev_id,))
        assert cur.fetchone()[0] >= 1, "心跳须打点 device_active"


def test_heartbeat_defaults_to_online(client, device_env):
    dev_id = device_env["devs"]["rbac_screen"]
    r = client.post(f"/api/v1/devices/{dev_id}/heartbeat",
                    headers=_h(device_env["token"]), json={})
    assert r.status_code == 200 and r.json()["data"]["status"] == "online"


def test_heartbeat_requires_device_role(client, device_env, tokens):
    dev_id = device_env["devs"]["rbac_screen"]
    for name in ("rbac_admin", "rbac_editor", "rbac_merchant"):
        r = client.post(f"/api/v1/devices/{dev_id}/heartbeat",
                        headers=_h(tokens[name]), json={})
        assert r.status_code == 403, f"{name} 不应有心跳权限"
    anon = client.post(f"/api/v1/devices/{dev_id}/heartbeat", json={})
    assert anon.status_code == 401


def test_heartbeat_scoped_to_own_venue(client, device_env):
    other_dev = device_env["devs"]["rbac-screen-b"]
    r = client.post(f"/api/v1/devices/{other_dev}/heartbeat",
                    headers=_h(device_env["token"]), json={})
    assert r.status_code == 403, "不得心跳其他场地/冒充他机（身份校验先于范围）"


def test_heartbeat_rejects_bad_status(client, device_env):
    dev_id = device_env["devs"]["rbac_screen"]
    r = client.post(f"/api/v1/devices/{dev_id}/heartbeat",
                    headers=_h(device_env["token"]), json={"status": "dancing"})
    assert r.status_code == 422


def test_devices_me_returns_own_row(client, device_env):
    r = client.get("/api/v1/devices/me", headers=_h(device_env["token"]))
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["code"] == "rbac_screen"
    assert data["device_id"] == device_env["devs"]["rbac_screen"]
    assert data["venue_id"] == device_env["accounts"]["vid"]


def test_devices_me_forbidden_for_admin(client, tokens):
    r = client.get("/api/v1/devices/me", headers=_h(tokens["rbac_admin"]))
    assert r.status_code == 403


def test_heartbeat_cannot_spoof_same_venue_device(client, device_env):
    """心跳绑定：device_id 必须等于 token 身份（同场地冒充 → 403）。"""
    import psycopg

    tid = device_env["accounts"]["tid"]
    with psycopg.connect(device_env["dsn"]) as conn, conn.cursor() as cur:
        cur.execute(
            "insert into devices (tenant_id, venue_id, code, name, device_type, status) "
            "values (%s, %s, 'rbac-screen-c2', '冒充目标', 'screen', 'offline') returning id",
            (tid, device_env["accounts"]["vid"]))
        other_id = cur.fetchone()[0]
        conn.commit()
    try:
        r = client.post(f"/api/v1/devices/{other_id}/heartbeat",
                        headers={"Authorization": f"Bearer {device_env['token']}"}, json={})
        assert r.status_code == 403, f"同场地冒充他机心跳应 403，实为 {r.status_code}"
    finally:
        with psycopg.connect(device_env["dsn"]) as conn, conn.cursor() as cur:
            cur.execute("delete from devices where id=%s", (other_id,))
            conn.commit()


