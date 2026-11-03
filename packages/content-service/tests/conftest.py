"""content-service 测试夹具：dsn + 测试账号（rbac_* 独立账号，不碰 seed 演示数据）。"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_dotenv() -> None:
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'").strip('"'))


_load_dotenv()

PASSWORD = "rbac-pass-123"


@pytest.fixture(scope="session")
def dsn() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL 未设置（复制 .env.example 为 .env）")
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


@pytest.fixture(scope="module")
def accounts(dsn):
    """三个测试身份：venue_admin / venue_editor / merchant（绑门店野莓茶集）。"""
    from platform_core.auth import hash_password

    spec = (("rbac_admin", "venue_admin", None),
            ("rbac_editor", "venue_editor", None),
            ("rbac_merchant", "merchant", "STORE"))
    hashed = hash_password(PASSWORD)
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("select id from tenants where code='shanqueli-demo'")
        tid = cur.fetchone()[0]
        cur.execute("select id from venues where tenant_id=%s limit 1", (tid,))
        vid = cur.fetchone()[0]
        cur.execute("select id from pois where tenant_id=%s and name='野莓茶集'", (tid,))
        store_poi = cur.fetchone()[0]
        users = {}
        for username, role, store in spec:
            cur.execute("delete from users where tenant_id=%s and username=%s",
                        (tid, username))
            cur.execute(
                "insert into users (tenant_id, username, password_hash, display_name) "
                "values (%s, %s, %s, 'rbac-test') returning id",
                (tid, username, hashed))
            uid = cur.fetchone()[0]
            cur.execute(
                "insert into user_roles (user_id, role_id, venue_id, merchant_id) "
                "values (%s, (select id from roles where code=%s), %s, %s)",
                (uid, role, vid, store_poi if store == "STORE" else None))
            users[username] = uid
        conn.commit()
    yield {"tid": tid, "vid": vid, "store_poi": store_poi,
           "users": users, "password": PASSWORD}
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        for username, _, _ in spec:
            cur.execute("delete from users where tenant_id=%s and username=%s",
                        (tid, username))
        conn.commit()


@pytest.fixture(scope="module")
def client(dsn):
    from content_service.app import create_app
    from fastapi.testclient import TestClient

    return TestClient(create_app(dsn=dsn))


@pytest.fixture(scope="module")
def tokens(client, accounts):
    """经 content-service 自身登录端点取三个角色的 token（同时验证 auth 挂载）。"""
    out = {}
    for username in ("rbac_admin", "rbac_editor", "rbac_merchant"):
        r = client.post("/api/v1/auth/login", json={
            "tenant_code": "shanqueli-demo", "username": username,
            "password": accounts["password"]})
        assert r.status_code == 200, f"{username} 登录失败：{r.text}"
        out[username] = r.json()["access_token"]
    return out


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
