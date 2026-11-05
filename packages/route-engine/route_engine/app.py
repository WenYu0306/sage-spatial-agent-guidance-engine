"""route-engine HTTP 服务（M0 契约形态）：兄弟模块经 HTTP 调用，禁止跨包 import。

POST /route/plan：业务错误（2003/2004）以 HTTP 200 + error_code 返回（M0 风格）。
"""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from .db import load_route_graph
from .graph import RouteError, build_graph, plan

app = FastAPI(title="route-engine", version="0.1.0")


class NearestNodeRequest(BaseModel):
    tenant_code: str
    venue_name: str
    floor_id: int
    x: float
    y: float


class PlanRequest(BaseModel):
    tenant_code: str
    venue_name: str
    start_node_id: int
    goal_node_id: int
    accessible_only: bool = False


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/route/plan/nearest-node")
def nearest_node(req: NearestNodeRequest) -> dict:
    """同层最近路网节点（M5 设施路线的起点解析；M2 服务化后 M5 不再直查路网）。"""
    import os

    import psycopg

    dsn = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "select n.id from route_nodes n join venues v on v.id=n.venue_id "
            "join tenants t on t.id=v.tenant_id "
            "where t.code=%s and v.name=%s and n.floor_id=%s and n.node_type='waypoint' "
            "order by (n.x-%s)^2+(n.y-%s)^2 limit 1",
            (req.tenant_code, req.venue_name, req.floor_id, req.x, req.y))
        row = cur.fetchone()
    return {"node_id": row[0]} if row else {"node_id": None}


@app.post("/route/plan")
def route_plan(req: PlanRequest) -> dict:
    try:
        nodes, edges, scale = load_route_graph(req.tenant_code, req.venue_name)
    except RouteError as exc:
        return {"error_code": exc.code, "message": str(exc)}
    except Exception:  # 13.2：脏场地（无 map_layers/无路网）曾是 500，按 PRD 降级 2004
        return {"error_code": 2004, "message": "路网未构建或数据不完整"}
    try:
        g = build_graph(nodes, edges, scale_meter=scale, accessible_only=req.accessible_only)
        r = plan(g, req.start_node_id, req.goal_node_id, scale_meter=scale)
    except RouteError as exc:
        return {"error_code": exc.code, "message": str(exc)}
    labels = _node_labels(req.tenant_code, req.venue_name, r.node_path)
    return {
        "node_path": r.node_path,
        "total_distance_meter": r.total_distance_meter,
        "total_time_s": r.total_time_s,
        "nodes": labels,
        "segments": [
            {"from_id": s.from_id, "to_id": s.to_id, "edge_type": s.edge_type,
             "distance_meter": s.distance_meter, "time_s": s.time_s}
            for s in r.segments
        ],
    }


def _node_labels(tenant_code: str, venue_name: str, node_ids: list[int]) -> dict:
    """节点 → {label, floor, x, y}（前端画线与文案需要；坐标随 M11/M12 接力复用）。"""
    import os

    import psycopg

    dsn = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "select n.id, coalesce(p.name, '走廊点(' || n.x::text || ',' || n.y::text || ')'), "
            "f.name, n.x, n.y from route_nodes n "
            "join floors f on f.id = n.floor_id "
            "join venues v on v.id = n.venue_id "
            "join tenants t on t.id = v.tenant_id "
            "left join pois p on p.id = n.poi_id "
            "where t.code = %s and v.name = %s and n.id = any(%s)",
            (tenant_code, venue_name, node_ids),
        )
        return {r[0]: {"label": r[1], "floor": r[2], "x": float(r[3]), "y": float(r[4])}
                for r in cur.fetchall()}
