"""M1 auth 核心单元测试：口令散列、JWT 签发/验证、锁定、黑名单（无网络依赖）。"""

from __future__ import annotations

import time

import bcrypt
import psycopg
import pytest
from platform_core.auth import (
    LockoutPolicy,
    TokenExpired,
    TokenInvalid,
    TokenSubject,
    decode_token,
    hash_password,
    is_locked,
    issue_tokens,
    register_failure,
    register_success,
    verify_password,
)

SECRET = "test-secret-0123456789abcdef0123456789"  # HS256 建议≥32 字节
SUB = TokenSubject(user_id=42, tenant_id=7, roles=["venue_admin"], venue_id=3)


# ---------- 口令 ----------

def test_password_roundtrip():
    hashed = hash_password("s3cret-口令")
    assert hashed != "s3cret-口令" and hashed.startswith("$2")
    assert verify_password("s3cret-口令", hashed)
    assert not verify_password("wrong", hashed)


def test_password_cost_is_12():
    hashed = hash_password("x")
    assert bcrypt.gensalt(rounds=12)[:7] == b"$2b$12$"
    assert hashed.startswith("$2b$12$"), "PRD 6.1：bcrypt cost>=12"


# ---------- JWT ----------

def test_issue_and_decode_access(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", SECRET)
    tokens = issue_tokens(SUB)
    assert tokens["token_type"] == "Bearer" and tokens["expires_in"] == 7200
    payload = decode_token(tokens["access_token"], SECRET)
    assert payload["sub"] == "42" and payload["tenant_id"] == 7
    assert payload["roles"] == ["venue_admin"] and payload["venue_id"] == 3
    assert payload["type"] == "access" and payload["jti"]
    assert payload["exp"] - payload["iat"] == 7200, "PRD 9：access 有效期 2h"


def test_refresh_token_minimal_claims(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", SECRET)
    tokens = issue_tokens(SUB)
    payload = decode_token(tokens["refresh_token"], SECRET, expected_type="refresh")
    assert payload["type"] == "refresh"
    assert payload["exp"] - payload["iat"] == 7 * 86400, "PRD 9：refresh 7d"
    assert "roles" not in payload, "refresh 最小化：不携带角色，刷新时重查库"


def test_expired_token_rejected(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", SECRET)
    tokens = issue_tokens(SUB, access_ttl=-1)
    with pytest.raises(TokenExpired):
        decode_token(tokens["access_token"], SECRET)


def test_tampered_token_rejected(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", SECRET)
    tokens = issue_tokens(SUB)
    head, body, sig = tokens["access_token"].split(".")
    with pytest.raises(TokenInvalid):
        decode_token(f"{head}.{body}.{sig[:-2]}AA", SECRET)


def test_wrong_type_rejected(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", SECRET)
    tokens = issue_tokens(SUB)
    with pytest.raises(TokenInvalid):
        decode_token(tokens["refresh_token"], SECRET, expected_type="access")


def test_missing_secret_refuses_to_sign():
    import os

    saved = os.environ.pop("JWT_SECRET", None)
    try:
        with pytest.raises(RuntimeError):
            issue_tokens(SUB)
    finally:
        if saved is not None:
            os.environ["JWT_SECRET"] = saved


# ---------- 黑名单 ----------

def test_blacklist_memory_revokes():
    from platform_core.auth import TokenBlacklist


    bl = TokenBlacklist(backend="memory")
    bl.add("jti-1", exp=time.time() + 60)
    assert bl.contains("jti-1")
    bl.add("jti-old", exp=time.time() - 1)
    time.sleep(0.01)
    assert not bl.contains("jti-old"), "过期条目应被视为不在黑名单"


def test_blacklist_redis_backend():
    redis = pytest.importorskip("redis")
    import os

    url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    try:
        client = redis.Redis.from_url(url, socket_connect_timeout=1)
        client.ping()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Redis 不可达：{exc}")
    from platform_core.auth import TokenBlacklist

    bl = TokenBlacklist(backend="redis", redis_url=url)
    bl.add("jti-redis-1", exp=time.time() + 60)
    assert bl.contains("jti-redis-1")
    assert client.ttl(bl._key("jti-redis-1")) > 0, "黑名单条目必须带 TTL（自动过期）"


# ---------- 锁定 ----------

POLICY = LockoutPolicy(max_attempts=3, window_seconds=900)


@pytest.fixture()
def lock_user(dsn):
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "insert into users (tenant_id, username, password_hash, display_name) "
            "values ((select id from tenants where code='shanqueli-demo'), "
            "'lock_test_user', 'x', 't') returning id")
        uid = cur.fetchone()[0]
        conn.commit()
    yield uid
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("delete from users where id=%s", (uid,))


def _user_row(dsn, uid):
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "select id, failed_logins, locked_until from users where id=%s", (uid,))
        return cur.fetchone()


def test_lockout_after_max_failures(dsn, lock_user):
    for _ in range(POLICY.max_attempts):
        register_failure(dsn, lock_user, POLICY)
    row = _user_row(dsn, lock_user)
    assert row[2] is not None, "达到失败上限应写 locked_until"
    assert is_locked(row)


def test_success_resets_counter(dsn, lock_user):
    register_failure(dsn, lock_user, POLICY)
    register_failure(dsn, lock_user, POLICY)
    register_success(dsn, lock_user)
    row = _user_row(dsn, lock_user)
    assert row[1] == 0 and row[2] is None


def test_is_locked_false_when_null_or_past():
    assert not is_locked((1, 0, None))
    assert not is_locked((1, 0, "2020-01-01 00:00:00+00:00"))
