"""M8 POI 写路径验收：CRUD + 发布状态机 + merchant 只能改自己门店（PRD 2.3 案例 3）。"""

from __future__ import annotations

import psycopg
import pytest


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


NEW_POI = {"category_code": "restaurant", "name": "测试茶餐厅", "intro": "测试用",
           "position_x": 100.0, "position_y": 200.0, "tags": ["测试"],
           "business_hours": {"mon": ["10:00-22:00"]}}


@pytest.fixture()
def floor_id(accounts, dsn):
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("select id from floors where venue_id=%s and level=1",
                    (accounts["vid"],))
        return cur.fetchone()[0]


@pytest.fixture()
def cleanup(dsn):
    made = []

    def add(poi_id: int):
        made.append(poi_id)

    yield add
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        for pid in made:
            cur.execute("delete from pois where id=%s", (pid,))
        conn.commit()


def _create(client, tokens, floor_id, accounts=None, **over):
    body = {**NEW_POI, "floor_id": floor_id, **over}
    if accounts:
        body.setdefault("venue_id", accounts["vid"])
    return client.post("/api/v1/pois", headers=_h(tokens["rbac_editor"]),
                       json=body)


def test_editor_creates_draft_then_submits(client, tokens, floor_id, cleanup, accounts):
    r = _create(client, tokens, floor_id, accounts)
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    cleanup(pid)
    assert r.json()["status"] == "draft", "新建 POI 落 draft 态"
    r = client.post(f"/api/v1/pois/{pid}/publish",
                    headers=_h(tokens["rbac_editor"]), json={"target": "pending"})
    assert r.json()["status"] == "pending", "editor 可提交审核"


def test_state_machine_valid_and_invalid(client, tokens, floor_id, cleanup, accounts):
    pid = _create(client, tokens, floor_id, accounts).json()["id"]
    cleanup(pid)
    h_admin = _h(tokens["rbac_admin"])
    # 非法跳转：draft 直接 published（409/4001，区别于越权 403/1003）
    r = client.post(f"/api/v1/pois/{pid}/publish", headers=h_admin,
                    json={"target": "published"})
    assert r.status_code == 409 and r.json()["error_code"] == 4001, "draft 不能直发"
    for target in ("pending", "published"):
        r = client.post(f"/api/v1/pois/{pid}/publish", headers=h_admin,
                        json={"target": target})
        assert r.json()["status"] == target
    client.post(f"/api/v1/pois/{pid}/publish", headers=h_admin,
                json={"target": "offline"})
    r = client.post(f"/api/v1/pois/{pid}/publish", headers=h_admin,
                    json={"target": "draft"})
    assert r.json()["status"] == "draft", "下架后可回草稿修订"


def test_editor_cannot_approve(client, tokens, floor_id, cleanup, accounts):
    pid = _create(client, tokens, floor_id, accounts).json()["id"]
    cleanup(pid)
    client.post(f"/api/v1/pois/{pid}/publish", headers=_h(tokens["rbac_editor"]),
                json={"target": "pending"})
    r = client.post(f"/api/v1/pois/{pid}/publish", headers=_h(tokens["rbac_editor"]),
                    json={"target": "published"})
    assert r.status_code == 403 and r.json()["error_code"] == 1003, "审核仅 venue_admin"


def test_merchant_can_edit_only_own_store(client, tokens, accounts, floor_id):
    """PRD 2.3 案例 3：商户 A 改商户 B（他店）资料 → 403/1003。"""
    ok = client.patch(f"/api/v1/pois/{accounts['store_poi']}",
                      headers=_h(tokens["rbac_merchant"]),
                      json={"intro": "本店主理人更新"})
    assert ok.status_code == 200
    with psycopg.connect(_dsn()) as conn, conn.cursor() as cur:
        cur.execute(
            "select id from pois where tenant_id=(select id from tenants "
            "where code='shanqueli-demo') and merchant_id is null "
            "and deleted_at is null and id <> %s limit 1", (accounts["store_poi"],))
        other_poi = cur.fetchone()[0]
    denied = client.patch(f"/api/v1/pois/{other_poi}",
                          headers=_h(tokens["rbac_merchant"]),
                          json={"intro": "越权"})
    assert denied.status_code == 403 and denied.json()["error_code"] == 1003


def test_soft_delete_hides_from_list(client, tokens, floor_id, cleanup, accounts):
    pid = _create(client, tokens, floor_id, accounts).json()["id"]
    cleanup(pid)
    r = client.delete(f"/api/v1/pois/{pid}", headers=_h(tokens["rbac_admin"]))
    assert r.status_code == 200
    listing = client.get("/api/v1/pois", headers=_h(tokens["rbac_admin"]),
                         params={"keyword": "测试茶餐厅"}).json()
    assert listing["items"] == [], "软删除后列表不可见"


def test_cross_tenant_venue_rejected(client, tokens, floor_id, accounts):
    r = _create(client, tokens, 999999, accounts)
    assert r.status_code == 403 and r.json()["error_code"] == 1003


def _dsn():
    import os

    return os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
