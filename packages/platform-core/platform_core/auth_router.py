"""M1 RBAC 的 FastAPI 装配：AuthRuntime（依赖工厂）+ /api/v1/auth 路由。

用法（宿主服务或测试 app）：
    runtime = AuthRuntime(dsn=Settings.from_env().database_url)
    app.include_router(create_auth_router(runtime))
    install_error_handlers(app)
    protected = Depends(runtime.dependency("venue_admin", "venue_editor"))

语义（PRD 2.2/2.3/9/10）：
- 无/坏/过期 token → 401 + 1001；角色不符或跨数据范围 → 403 + 1003
  （不得返回空列表伪装成功）；403 写 operation_logs（action=access_denied）。
- 凭证类失败（账号不存在/口令错/锁定/租户停用）统一 401 + 1001，
  不区分具体原因（防用户枚举）；登录成功/失败均写 operation_logs(action=login)。
- access token 携带角色与数据范围；refresh 最小化，刷新时按库重查角色并
  轮换（旧 refresh jti 进黑名单）。
"""

from __future__ import annotations

from dataclasses import dataclass

import psycopg
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from psycopg.types.json import Jsonb
from pydantic import BaseModel

from . import auth
from .auth import LockoutPolicy, TokenBlacklist, TokenSubject


class AuthError(Exception):
    def __init__(self, status_code: int, error_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.message = message


@dataclass(frozen=True)
class AuthContext:
    """从 access token 解出的身份与数据范围（服务层据此强制注入过滤条件）。"""

    user_id: int
    tenant_id: int
    roles: list[str]
    venue_id: int | None
    merchant_id: int | None
    device_id: int | None
    _runtime: "AuthRuntime"
    trace_id: str | None = None
    ip: str | None = None

    @property
    def is_device(self) -> bool:
        return "device" in self.roles

    def _deny(self, message: str, object_type: str, object_id: int | None):
        self._runtime.oplog(
            tenant_id=self.tenant_id, user_id=self.user_id, action="access_denied",
            object_type=object_type, object_id=object_id, trace_id=self.trace_id,
            ip=self.ip)
        raise AuthError(403, 1003, message)

    def ensure_venue(self, venue_id: int) -> None:
        """URL/参数里的场地必须等于 token 的场地范围（PRD 2.3 案例 2）。"""
        if self.venue_id is not None and venue_id != self.venue_id:
            self._deny("你没有该场地的权限", "venue", venue_id)

    def ensure_merchant(self, poi_id: int) -> None:
        """merchant 只能写绑定的门店（PRD 2.3 案例 3）。"""
        if self.merchant_id is not None and poi_id != self.merchant_id:
            self._deny("你没有该门店的操作权限", "poi", poi_id)


class AuthRuntime:
    """持 DSN/黑名单/锁定策略，产出路由与依赖。一个宿主 app 建一个实例。"""

    def __init__(self, dsn: str, blacklist: TokenBlacklist | None = None,
                 policy: LockoutPolicy | None = None):
        self.dsn = dsn
        self.blacklist = blacklist or TokenBlacklist()
        self.policy = policy or LockoutPolicy.from_env()

    def _authed_ctx(self, request: Request,
                    allowed_roles: tuple[str, ...] = ()) -> AuthContext:
        """验 token → 验角色 → 交出 AuthContext（dependency/optional 共用路径）。"""
        header = request.headers.get("authorization", "")
        if not header.startswith("Bearer "):
            raise AuthError(401, 1001, "缺少 Bearer 凭证")
        token = header[len("Bearer "):]
        try:
            payload = auth.decode_token(
                token, expected_type="access", blacklist=self.blacklist)
        except auth.TokenError as exc:
            raise AuthError(401, 1001, str(exc)) from exc
        roles = list(payload.get("roles") or [])
        if allowed_roles and not set(roles) & set(allowed_roles):
            ctx = self._context(payload, request)
            ctx._deny("你没有该操作的权限", "api", None)
        return self._context(payload, request)

    def dependency(self, *allowed_roles: str):
        """FastAPI 依赖工厂：验 token → 验角色 → 交出 AuthContext。"""

        def dep(request: Request) -> AuthContext:
            return self._authed_ctx(request, allowed_roles)

        return dep

    def optional(self, venue_query_key: str = "venue_id"):
        """guest 可用依赖（PRD 595"Authorization guest 除外"）：
        无 token 时以 ?venue_id= 反查匿名身份——租户自 active 场地反查，
        绝不信任客户端给的 tenant_id；带 token 则走与 dependency() 相同路径。"""

        def dep(request: Request) -> AuthContext:
            if not request.headers.get("authorization", "").startswith("Bearer "):
                raw = request.query_params.get(venue_query_key) or ""
                if not raw.isdigit():
                    raise AuthError(401, 1001, "缺少 Bearer 凭证（guest 需提供 venue_id）")
                with psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
                    cur.execute(
                        "select id, tenant_id from venues where id=%s and status='active'",
                        (int(raw),))
                    row = cur.fetchone()
                if not row:
                    raise AuthError(401, 1001, "场地不存在或未开放")
                return AuthContext(user_id=0, tenant_id=row[1], roles=["guest"],
                                   venue_id=row[0], merchant_id=None, device_id=None,
                                   _runtime=self,
                                   trace_id=request.headers.get("X-Trace-Id"),
                                   ip=request.client.host if request.client else None)
            return self._authed_ctx(request)

        return dep

    def _context(self, payload: dict, request: Request) -> AuthContext:
        return AuthContext(
            user_id=int(payload.get("sub", "0")),
            tenant_id=payload.get("tenant_id", 0),
            roles=list(payload.get("roles") or []),
            venue_id=payload.get("venue_id"),
            merchant_id=payload.get("merchant_id"),
            device_id=payload.get("device_id"),
            _runtime=self,
            trace_id=request.headers.get("X-Trace-Id"),
            ip=request.client.host if request.client else None,
        )

    def oplog(self, tenant_id: int, user_id: int | None, action: str,
              object_type: str, object_id: int | None = None,
              trace_id: str | None = None, ip: str | None = None,
              diff: dict | None = None) -> None:
        try:
            with psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
                cur.execute(
                    "insert into operation_logs (tenant_id, user_id, action, "
                    "object_type, object_id, diff, ip, trace_id) "
                    "values (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (tenant_id, user_id, action, object_type, object_id,
                     Jsonb(diff) if diff else None, ip, trace_id))
        except psycopg.Error:
            pass  # 审计失败不阻断主流程；生产以日志告警兜底（M13 接告警）


class _LoginRequest(BaseModel):
    tenant_code: str
    username: str
    password: str


class _RefreshRequest(BaseModel):
    refresh_token: str


def create_auth_router(runtime: AuthRuntime) -> APIRouter:
    router = APIRouter()

    def _deny_401(message: str) -> JSONResponse:
        return JSONResponse(status_code=401,
                            content={"error_code": 1001, "message": message})

    def _load_identity(cur, user_id: int, tenant_id: int):
        """按库重查角色与范围（刷新/登录共用：角色永不过期于 token 之外）。

        device 角色附带 devices.id（auth.py 约定"device 身份时 device_id 必填"，
        以 devices.code == users.username 关联——设备账号与设备行同名成对）。
        """
        cur.execute(
            "select r.code, ur.venue_id, ur.merchant_id, u.display_name, u.username "
            "from users u left join user_roles ur on ur.user_id = u.id "
            "left join roles r on r.id = ur.role_id "
            "where u.id=%s and u.tenant_id=%s and u.status='active'",
            (user_id, tenant_id))
        rows = cur.fetchall()
        if not rows:
            return None
        roles = [r[0] for r in rows if r[0]]
        device_id = None
        if "device" in roles:
            cur.execute(
                "select id from devices where tenant_id=%s and code=%s",
                (tenant_id, rows[0][4]))
            drow = cur.fetchone()
            device_id = drow[0] if drow else None
        return {"roles": roles, "venue_id": rows[0][1], "merchant_id": rows[0][2],
                "display_name": rows[0][3], "device_id": device_id}

    @router.post("/api/v1/auth/login")
    def login(body: _LoginRequest, request: Request):
        ip = request.client.host if request.client else None
        trace_id = request.headers.get("X-Trace-Id")
        with psycopg.connect(runtime.dsn) as conn, conn.cursor() as cur:
            cur.execute("select id, status from tenants where code=%s",
                        (body.tenant_code,))
            trow = cur.fetchone()
            urow = None
            if trow and trow[1] == "active":
                cur.execute(
                    "select id, password_hash, status, failed_logins, locked_until "
                    "from users where tenant_id=%s and username=%s",
                    (trow[0], body.username))
                urow = cur.fetchone()
            # is_locked 约定 3 元组 (id, failed_logins, locked_until)
            if urow and auth.is_locked((urow[0], urow[3], urow[4])):
                runtime.oplog(trow[0], urow[0], "login", "user", urow[0],
                              trace_id, ip, diff={"result": "locked"})
                return _deny_401("账号已锁定，请稍后再试")
            if not urow or urow[2] != "active" or not auth.verify_password(
                    body.password, urow[1]):
                if urow:
                    auth.register_failure(runtime.dsn, urow[0], runtime.policy)
                if trow:
                    runtime.oplog(trow[0], urow[0] if urow else None, "login",
                                  "user", urow[0] if urow else None, trace_id, ip,
                                  diff={"result": "failed"})
                return _deny_401("租户、账号或口令不正确")
            uid, tid = urow[0], trow[0]
            auth.register_success(runtime.dsn, uid)
            ident = _load_identity(cur, uid, tid)
            tokens = auth.issue_tokens(TokenSubject(
                user_id=uid, tenant_id=tid, roles=ident["roles"],
                venue_id=ident["venue_id"], merchant_id=ident["merchant_id"],
                device_id=ident["device_id"]))
            runtime.oplog(tid, uid, "login", "user", uid, trace_id, ip,
                          diff={"result": "ok"})
            return {**tokens, "display_name": ident["display_name"],
                    "roles": ident["roles"], "venue_id": ident["venue_id"],
                    "device_id": ident["device_id"]}

    @router.post("/api/v1/auth/refresh")
    def refresh(body: _RefreshRequest, request: Request):
        try:
            payload = auth.decode_token(
                body.refresh_token, expected_type="refresh",
                blacklist=runtime.blacklist)
        except auth.TokenError as exc:
            return _deny_401(str(exc))
        with psycopg.connect(runtime.dsn) as conn, conn.cursor() as cur:
            ident = _load_identity(cur, int(payload["sub"]), payload["tenant_id"])
            if not ident:
                return _deny_401("账号不可用")
            tokens = auth.issue_tokens(TokenSubject(
                user_id=int(payload["sub"]), tenant_id=payload["tenant_id"],
                roles=ident["roles"], venue_id=ident["venue_id"],
                merchant_id=ident["merchant_id"], device_id=ident["device_id"]))
        runtime.blacklist.add(payload["jti"], exp=payload["exp"])  # 轮换：旧 refresh 作废
        return {**tokens, "display_name": ident["display_name"],
                "roles": ident["roles"], "venue_id": ident["venue_id"]}

    return router


def install_error_handlers(app) -> None:
    """AuthError → 统一包络 {"error_code", "message"}（顶层，非 detail 嵌套）。"""

    @app.exception_handler(AuthError)
    def _handler(request, exc: AuthError):
        return JSONResponse(status_code=exc.status_code,
                            content={"error_code": exc.error_code,
                                     "message": exc.message})
