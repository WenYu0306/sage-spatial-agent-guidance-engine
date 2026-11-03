"""单模块演示：登录 → POI 状态机 → 领券幂等（cd packages/content-service && make demo）。"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient

from .app import create_app


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
    client = TestClient(create_app(dsn=dsn))
    r = client.post("/api/v1/auth/login", json={
        "tenant_code": "shanqueli-demo", "username": "demo_admin", "password": password})
    if r.status_code != 200:
        raise SystemExit(f"登录失败：{r.text}")
    body = r.json()
    print(f"demo_admin 登录 → roles={body['roles']} venue_id={body['venue_id']}")
    h = {"Authorization": f"Bearer {body['access_token']}"}

    pois = client.get("/api/v1/pois", headers=h,
                      params={"keyword": "火锅", "page_size": 5}).json()
    print(f"POI 列表（keyword=火锅）→ {pois['total']} 条："
          f"{[i['name'] for i in pois['items']]}")

    floor = client.get(f"/api/v1/venues/{body['venue_id']}/floors", headers=h
                       ).json()["items"][1]
    created = client.post("/api/v1/pois", headers=h, json={
        "venue_id": body["venue_id"], "floor_id": floor["id"],
        "category_code": "restaurant", "name": "演示快闪茶铺",
        "position_x": 500.0, "position_y": 500.0, "tags": ["演示"]}).json()
    pid = created["id"]
    print(f"新建 POI {pid} → {created['status']}")
    for target in ("pending", "published"):
        r = client.post(f"/api/v1/pois/{pid}/publish", headers=h,
                        json={"target": target})
        print(f"  发布 → {target}: {r.json()}")
    r = client.post(f"/api/v1/pois/{pid}/publish", headers=h,
                    json={"target": "offline"})
    print(f"  下架 → {r.json()}")
    with_demo = client.get(f"/api/v1/pois/{pid}", headers=h).json()
    print(f"  详情：status={with_demo['status']} activities={len(with_demo['activities'])}")

    coupons = client.get("/api/v1/coupons", headers=h).json()["items"]
    if coupons:
        cid = coupons[0]["id"]
        r1 = client.post(f"/api/v1/coupons/{cid}/claim", json={"anonymous_id": "demo-guest"})
        r2 = client.post(f"/api/v1/coupons/{cid}/claim", json={"anonymous_id": "demo-guest"})
        print(f"领券 {cid}：首领 duplicate={r1.json().get('duplicate')}，"
              f"重放 duplicate={r2.json().get('duplicate')}（库存只扣一次）")
    # demo 自清理：演示 POI 行不残留（硬删仅限 demo 自建行）
    import psycopg

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("delete from pois where id=%s", (pid,))
        conn.commit()
    print("（演示 POI 已清理；完整状态机/越权/幂等矩阵见 tests/）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
