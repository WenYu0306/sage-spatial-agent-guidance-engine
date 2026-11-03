"""HTTP 服务测试（TestClient + 真库）：health、规划 200、2003 语义在 200 体中。"""

from __future__ import annotations

from fastapi.testclient import TestClient
from route_engine.app import app

client = TestClient(app)


def _poi_node_ids():
    import os

    import psycopg
    from route_engine.db import load_route_graph

    nodes, _edges, _scale = load_route_graph("shanqueli-demo", "山雀里·栖云广场")
    poi_nodes = {v.poi_id: k for k, v in nodes.items() if v.poi_id}
    dsn = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("select name, id from pois where name in ('云雀优选超市', '巨幕星云影院')")
        ids = dict(cur.fetchall())
    return poi_nodes[ids["云雀优选超市"]], poi_nodes[ids["巨幕星云影院"]]


def test_health():
    assert client.get("/health").json()["ok"] is True


def test_plan_returns_segments():
    start, goal = _poi_node_ids()
    r = client.post(
        "/route/plan",
        json={"tenant_code": "shanqueli-demo", "venue_name": "山雀里·栖云广场",
              "start_node_id": start, "goal_node_id": goal},
    )
    body = r.json()
    assert r.status_code == 200 and "error_code" not in body
    assert len(body["segments"]) >= 8 and body["total_time_s"] > 0


def test_plan_unknown_node_is_business_error_2003():
    start, goal = _poi_node_ids()
    r = client.post(
        "/route/plan",
        json={"tenant_code": "shanqueli-demo", "venue_name": "山雀里·栖云广场",
              "start_node_id": 999999, "goal_node_id": goal},
    )
    body = r.json()
    assert r.status_code == 200
    assert body["error_code"] == 2003, "业务错误以 200 + error_code 表达（M0 风格）"
