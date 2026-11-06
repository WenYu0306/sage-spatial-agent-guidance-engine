"""M1 认证核心：bcrypt 口令、JWT 签发/验证、登录锁定、token 黑名单。

策略（PRD 9 安全表 + D-019）：HS256 + JWT_SECRET（环境变量，缺省拒绝签发）；
access 2h / refresh 7d；access 携带角色与数据范围，refresh 最小化（刷新时重查库）。
登录锁定：连续失败 max_attempts 次锁 window_seconds 秒（users.failed_logins /
locked_until 字段 PRD 6.1 已备）。登出黑名单：REDIS_URL 可达用 Redis（带 TTL 自动
过期），降级进程内存（单进程 demo 足够，多副本部署必须 Redis）。
本模块不做 HTTP 与路由（见 auth_router.py）；直接持 DSN 做锁定计数。
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

import bcrypt
import jwt
import psycopg

# ---------- 异常层级（错误码对齐 PRD 10：1001 参数/凭证无效） ----------

class TokenError(Exception):
    error_code = 1001


class TokenInvalid(TokenError):
    pass


class TokenExpired(TokenInvalid):
    pass


class TokenRevoked(TokenInvalid):
    pass


# ---------- 口令（bcrypt cost>=12，PRD 6.1） ----------

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


# ---------- JWT ----------

@dataclass(frozen=True)
class TokenSubject:
    """access token 的身份载荷；device 身份时 device_id 必填。"""

    user_id: int
    tenant_id: int
    roles: list[str] = field(default_factory=list)
    venue_id: int | None = None
    merchant_id: int | None = None
    device_id: int | None = None


_PUBLIC_PLACEHOLDER_SECRETS = frozenset({
    # .env.example 曾随仓库公开发布的示例值（审查 C11）——任何环境都不得用其签发
    "change_me_demo_secret_0123456789abcdef",
})


def _secret() -> str:
    secret = os.environ.get("JWT_SECRET", "")
    if not secret:
        raise RuntimeError("JWT_SECRET 未设置：拒绝签发（密钥必须来自环境变量）")
    if secret in _PUBLIC_PLACEHOLDER_SECRETS or len(secret) < 32:
        raise RuntimeError(
            "JWT_SECRET 为公开示例值或强度不足（<32 字符）：拒绝签发；"
            "生成方式：openssl rand -hex 32")
    return secret


def issue_tokens(subject: TokenSubject, access_ttl: int = 7200,
                 refresh_ttl: int = 7 * 86400) -> dict:
    """签发 access+refresh；token_type/expires_in 字段名对齐 OAuth 惯例。"""
    secret = _secret()
    now = int(time.time())
    base = {"sub": str(subject.user_id), "tenant_id": subject.tenant_id,
            "iat": now, "jti": uuid4_hex()}
    access = {**base, "type": "access", "exp": now + access_ttl,
              "roles": subject.roles, "venue_id": subject.venue_id,
              "merchant_id": subject.merchant_id, "device_id": subject.device_id}
    refresh = {**base, "type": "refresh", "exp": now + refresh_ttl}
    return {
        "access_token": jwt.encode(access, secret, algorithm="HS256"),
        "refresh_token": jwt.encode(refresh, secret, algorithm="HS256"),
        "token_type": "Bearer",
        "expires_in": access_ttl,
    }


def decode_token(token: str, secret: str | None = None, expected_type: str = "access",
                 blacklist=None) -> dict:
    """验证并解包；黑名单传入则先查 jti。失败抛 TokenError 子类。"""
    secret = secret if secret is not None else _secret()
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpired("token 已过期") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenInvalid("token 无效") from exc
    if payload.get("type") != expected_type:
        raise TokenInvalid("token 类型不匹配")
    if blacklist is not None and blacklist.contains(payload.get("jti", "")):
        raise TokenRevoked("token 已登出")
    return payload


def uuid4_hex() -> str:
    import uuid

    return uuid.uuid4().hex


# ---------- 黑名单（Redis 带 TTL 自动过期；降级进程内存） ----------

class TokenBlacklist:
    def __init__(self, backend: str | None = None, redis_url: str | None = None):
        backend = backend or (os.environ.get("TOKEN_BLACKLIST_BACKEND", "") or None)
        self._client = None
        self._mem: dict[str, float] = {}
        if backend == "redis" or (backend is None and redis_url):
            import redis

            self._client = redis.Redis.from_url(
                redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
                socket_connect_timeout=1,
            )

    def _key(self, jti: str) -> str:
        return f"sage:token_bl:{jti}"

    def add(self, jti: str, exp: float) -> None:
        ttl = max(1, int(exp - time.time()))
        if self._client is not None:
            self._client.set(self._key(jti), "1", ex=ttl)
        else:
            self._mem[jti] = exp

    def contains(self, jti: str) -> bool:
        if not jti:
            return False
        if self._client is not None:
            return bool(self._client.exists(self._key(jti)))
        now = time.time()
        self._mem = {k: v for k, v in self._mem.items() if v > now}
        return self._mem.get(jti, 0) > now


# ---------- 登录锁定（PRD 6.1 字段；策略可配） ----------

@dataclass(frozen=True)
class LockoutPolicy:
    max_attempts: int = 5
    window_seconds: int = 900

    @classmethod
    def from_env(cls) -> "LockoutPolicy":
        return cls(
            max_attempts=int(os.environ.get("LOCKOUT_MAX_ATTEMPTS", "5")),
            window_seconds=int(os.environ.get("LOCKOUT_SECONDS", "900")),
        )


def is_locked(user_row: tuple) -> bool:
    """user_row: (id, failed_logins, locked_until)；locked_until 在未来即锁定。"""
    locked_until = user_row[2]
    if locked_until is None:
        return False
    if isinstance(locked_until, str):
        from datetime import datetime

        locked_until = datetime.fromisoformat(locked_until)
    return locked_until.timestamp() > time.time()


def register_failure(dsn: str, user_id: int, policy: LockoutPolicy) -> None:
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "update users set failed_logins = failed_logins + 1 where id=%s", (user_id,))
        cur.execute("select failed_logins from users where id=%s", (user_id,))
        if cur.fetchone()[0] >= policy.max_attempts:
            # make_interval 而非 interval '%s seconds'（审查 A3）：psycopg 会把
            # 字面量里的 %s 转成 $1 占位符文本，Postgres 将其解析为 1 秒——
            # 锁定窗口与配置无关，形同虚设。
            cur.execute(
                "update users set locked_until = now() + make_interval(secs => %s) "
                "where id=%s", (policy.window_seconds, user_id))


def register_success(dsn: str, user_id: int) -> None:
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "update users set failed_logins=0, locked_until=NULL, last_login_at=now() "
            "where id=%s", (user_id,))
