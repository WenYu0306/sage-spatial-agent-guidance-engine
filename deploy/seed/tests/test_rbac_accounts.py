"""M1 RBAC 数据层验收：演示账号/角色绑定/设备行由 seed 幂等创建。

手册任务（M1 完整 RBAC）子任务 1。需要 DATABASE_URL 与 SEED_DEMO_ADMIN_PASSWORD
（conftest 自动读 .env）。断言矩阵（PRD 2.1/2.2 对应）：
demo_admin=venue_admin、demo_editor=venue_editor、demo_merchant=merchant（绑定门店 POI）、
设备行 screen-f1-01。重复 seed 不得覆写口令。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import bcrypt
import psycopg
import pytest

SEED_PY = Path(__file__).resolve().parents[1] / "seed.py"

ACCOUNT_ROLES = {
    "demo_admin": "venue_admin",
    "demo_editor": "venue_editor",
    "demo_merchant": "merchant",
}
MERCHANT_STORE = "野莓茶集"


@pytest.fixture(scope="module")
def seed_mod():
    spec = importlib.util.spec_from_file_location("sage_seed", SEED_PY)
    assert spec and spec.loader, "无法加载 deploy/seed/seed.py"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def tid(seed_mod):
    seed_mod.run_seed()
    with psycopg.connect(seed_mod._dsn()) as conn, conn.cursor() as cur:
        cur.execute("select id from tenants where code='shanqueli-demo'")
        return cur.fetchone()[0]


def _account(cur, tid: int, username: str):
    cur.execute(
        "select u.id, r.code, ur.venue_id, ur.merchant_id "
        "from users u left join user_roles ur on ur.user_id = u.id "
        "left join roles r on r.id = ur.role_id "
        "where u.tenant_id=%s and u.username=%s",
        (tid, username),
    )
    return cur.fetchone()


def test_demo_accounts_exist_with_roles(tid):
    with psycopg.connect(seed_mod_dsn()) as conn, conn.cursor() as cur:
        for username, role in ACCOUNT_ROLES.items():
            row = _account(cur, tid, username)
            assert row and row[0], f"{username} 账号缺失"
            assert row[1] == role, f"{username} 角色应为 {role}，实际 {row[1]}"


def seed_mod_dsn():
    import os

    return os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)


def test_merchant_bound_to_store_poi(tid):
    with psycopg.connect(seed_mod_dsn()) as conn, conn.cursor() as cur:
        row = _account(cur, tid, "demo_merchant")
        assert row and row[3], "demo_merchant 未绑定门店（user_roles.merchant_id 为空）"
        cur.execute(
            "select p.name from pois p where p.id=%s and p.tenant_id=%s", (row[3], tid)
        )
        got = cur.fetchone()
        assert got and got[0] == MERCHANT_STORE, f"绑定门店应为 {MERCHANT_STORE}，实际 {got}"


def test_demo_device_row(tid):
    with psycopg.connect(seed_mod_dsn()) as conn, conn.cursor() as cur:
        cur.execute(
            "select d.id, d.device_type, d.status from devices d "
            "join venues v on v.id=d.venue_id join tenants t on t.id=v.tenant_id "
            "where t.code='shanqueli-demo' and d.code='screen-f1-01'"
        )
        row = cur.fetchone()
        assert row, "设备 screen-f1-01 缺失"
        assert row[1] == "screen"
        # status 可能被运行中的大屏心跳合法置为 online（F-19），种子初始为 offline
        assert row[2] in ("offline", "online")


def test_password_verifies_with_seed_env(tid):
    password = os_environ_password()
    if not password:
        pytest.skip("SEED_DEMO_ADMIN_PASSWORD 未设置")
    with psycopg.connect(seed_mod_dsn()) as conn, conn.cursor() as cur:
        row = _account(cur, tid, "demo_admin")
        cur.execute("select password_hash from users where id=%s", (row[0],))
        hashed = cur.fetchone()[0]
        assert bcrypt.checkpw(password.encode(), hashed.encode()), "口令与 SEED 环境变量不符"


def os_environ_password():
    import os

    return os.environ.get("SEED_DEMO_ADMIN_PASSWORD", "")


def test_reseed_never_overwrites_password(seed_mod, tid):
    new_hash = bcrypt.hashpw(b"changed-by-test", bcrypt.gensalt(rounds=12)).decode()
    with psycopg.connect(seed_mod_dsn()) as conn, conn.cursor() as cur:
        row = _account(cur, tid, "demo_editor")
        cur.execute("select password_hash from users where id=%s", (row[0],))
        original = cur.fetchone()[0]
        cur.execute("update users set password_hash=%s where id=%s", (new_hash, row[0]))
        conn.commit()
        try:
            seed_mod.run_seed()
            cur.execute("select password_hash from users where id=%s", (row[0],))
            assert cur.fetchone()[0] == new_hash, "重复 seed 覆写了口令（幂等纪律）"
        finally:
            # 还原现场：测试不得留下被改写的演示账号口令
            cur.execute("update users set password_hash=%s where id=%s",
                        (original, row[0]))
            conn.commit()
