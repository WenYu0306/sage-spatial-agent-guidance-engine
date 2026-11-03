"""platform-core 单模块演示：起一个带 auth 路由 + 受保护 stub 的 app，
演示四角色登录、越权拦截（PRD 2.3 三类）、刷新轮换与锁定。

cd packages/platform-core && make demo
前置：make migrate && make seed（SEED_DEMO_ADMIN_PASSWORD 已设）+ JWT_SECRET 入 .env。
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from .auth_router import AuthRuntime, create_auth_router, install_error_handlers


def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parents[3] / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip("'").strip('"'))


def main() -> int:
    _load_dotenv()
    dsn = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
    password = os.environ.get("SEED_DEMO_ADMIN_PASSWORD", "")
    if not password:
        raise SystemExit("SEED_DEMO_ADMIN_PASSWORD 未设置（.env）")
    runtime = AuthRuntime(dsn=dsn)
    app = FastAPI(title="platform-core auth demo")
    app.include_router(create_auth_router(runtime))
    install_error_handlers(app)

    @app.get("/api/v1/admin/accounts")
    def accounts(ctx=Depends(runtime.dependency("platform_admin", "venue_admin"))):
        return {"ok": True, "as": ctx.roles}

    @app.post("/api/v1/demo/stores/{poi_id}")
    def store(poi_id: int, ctx=Depends(runtime.dependency("merchant"))):
        ctx.ensure_merchant(poi_id)
        return {"ok": True}

    client = TestClient(app)

    print("== 1) 三个演示角色登录 ==")
    tokens = {}
    for username, label in (("demo_admin", "venue_admin"), ("demo_editor", "venue_editor"),
                            ("demo_merchant", "merchant")):
        r = client.post("/api/v1/auth/login", json={
            "tenant_code": "shanqueli-demo", "username": username, "password": password})
        body = r.json()
        if "access_token" not in body:  # 账号被锁等场景：如实打印而不是崩
            print(f"  {username:14s} → HTTP {r.status_code} {body}")
            continue
        tokens[username] = body["access_token"]
        print(f"  {username:14s} → roles={body['roles']} venue_id={body['venue_id']} "
              f"expires_in={body['expires_in']}s")

    print("== 2) 角色与数据范围拦截（PRD 2.3）==")
    cases = [
        ("editor 调账号管理", client.get("/api/v1/admin/accounts",
             headers={"Authorization": f"Bearer {tokens['demo_editor']}"})),
        ("merchant 改别家门店", client.post("/api/v1/demo/stores/1",
             headers={"Authorization": f"Bearer {tokens['demo_merchant']}"})),
        ("无凭证访问后台", client.get("/api/v1/admin/accounts")),
    ]
    for label, r in cases:
        print(f"  {label:18s} → HTTP {r.status_code} {r.json()}")

    print("== 3) 错误口令 → 失败计数；正确口令仍可登录 ==")
    r = client.post("/api/v1/auth/login", json={
        "tenant_code": "shanqueli-demo", "username": "demo_admin", "password": "nope"})
    print(f"  错误口令 → HTTP {r.status_code} {r.json()}")
    r = client.post("/api/v1/auth/login", json={
        "tenant_code": "shanqueli-demo", "username": "demo_admin", "password": password})
    print(f"  正确口令 → HTTP {r.status_code} roles={r.json().get('roles')}")

    print("== 4) refresh 轮换：旧 refresh 再用即失效 ==")
    login = client.post("/api/v1/auth/login", json={
        "tenant_code": "shanqueli-demo", "username": "demo_admin",
        "password": password}).json()
    r1 = client.post("/api/v1/auth/refresh",
                     json={"refresh_token": login["refresh_token"]})
    r2 = client.post("/api/v1/auth/refresh",
                     json={"refresh_token": login["refresh_token"]})
    print(f"  第一次刷新 → HTTP {r1.status_code}（新 token 对）")
    print(f"  旧值重放 → HTTP {r2.status_code} {r2.json()}")
    print("（完整越权五连与黑名单/锁定细节见 tests/test_rbac_api.py）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
