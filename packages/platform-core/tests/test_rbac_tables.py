"""M1 迁移 0006 验收：user_roles / devices / operation_logs 三表按 PRD 6.1 建立。

先跑 alembic upgrade head（子进程，等价 make migrate），再查 information_schema。
PRD 的 user_roles 主键 (user_id, role_id, venue_id) 与 venue_id 可空矛盾（NULL 不能进
PK）——实现用表达式唯一索引 UNIQUE (user_id, role_id, COALESCE(venue_id,0),
COALESCE(merchant_id,0)) 达成同一语义，偏差记录于迁移 docstring 与 DECISIONS。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import psycopg
import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module", autouse=True)
def _migrated():
    subprocess.run(
        ["uv", "run", "alembic", "-c", "deploy/migrations/alembic.ini", "upgrade", "head"],
        cwd=ROOT, check=True, capture_output=True,
    )


def _columns(cur, table: str) -> dict:
    cur.execute(
        "select column_name, is_nullable from information_schema.columns "
        "where table_name=%s", (table,))
    return {r[0]: r[1] for r in cur.fetchall()}


def test_rbac_tables_exist(dsn):
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        for table in ("user_roles", "devices", "operation_logs"):
            cur.execute(
                "select 1 from information_schema.tables where table_name=%s", (table,))
            assert cur.fetchone(), f"表 {table} 不存在（0006 未生效）"


def test_user_roles_columns_and_scope(dsn):
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cols = _columns(cur, "user_roles")
        for col in ("user_id", "role_id", "venue_id", "merchant_id"):
            assert col in cols, f"user_roles 缺列 {col}"
        assert cols["venue_id"] == "YES" and cols["merchant_id"] == "YES"


def test_user_roles_unique_semantics(dsn):
    """同 (user, role, NULL venue) 重复绑定必须被表达式唯一索引拦截。"""
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("select id from roles where code='venue_admin' limit 1")
        role_id = cur.fetchone()[0]
        cur.execute(
            "insert into users (tenant_id, username, password_hash, display_name) "
            "values ((select id from tenants where code='shanqueli-demo'), "
            "'rbac_t_user', 'x', 't') returning id")
        uid = cur.fetchone()[0]
        try:
            cur.execute(
                "insert into user_roles (user_id, role_id) values (%s, %s)", (uid, role_id))
            with pytest.raises(psycopg.errors.UniqueViolation):
                cur.execute(
                    "insert into user_roles (user_id, role_id) values (%s, %s)",
                    (uid, role_id))
        finally:
            conn.rollback()


def test_devices_columns(dsn):
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cols = _columns(cur, "devices")
        for col in ("tenant_id", "venue_id", "code", "device_type",
                    "position_x", "position_y", "status", "last_seen_at"):
            assert col in cols, f"devices 缺列 {col}"


def test_operation_logs_columns(dsn):
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cols = _columns(cur, "operation_logs")
        for col in ("tenant_id", "user_id", "action", "object_type", "diff", "trace_id"):
            assert col in cols, f"operation_logs 缺列 {col}"
