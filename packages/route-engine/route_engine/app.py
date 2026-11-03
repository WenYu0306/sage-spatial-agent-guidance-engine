"""route-engine HTTP 服务（M0 契约形态）：兄弟模块经 HTTP 调用，禁止跨包 import。

POST /route/plan：业务错误（2003/2004）以 HTTP 200 + error_code 返回（M0 风格）。
"""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from .db import load_route_graph
from .graph import RouteError, build_graph, plan

app = FastAPI(title="route-engine", version="0.1.0")


class PlanRequest(BaseModel):
    tenant_code: str
    venue_name: str
    start_node_id: int
    goal_node_id: int
    accessible_only: bool = False


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/route/plan")
def route_plan(req: PlanRequest) -> dict:
    try:
        nodes, edges, scale = load_route_graph(req.tenant_code, req.venue_name)
        g = build_graph(nodes, edges, scale_meter=scale, accessible_only=req.accessible_only)
        r = plan(g, req.start_node_id, req.goal_node_id, scale_meter=scale)
    except RouteError as exc:
        return {"error_code": exc.code, "message": str(exc)}
    return {
        "node_path": r.node_path,
        "total_distance_meter": r.total_distance_meter,
        "total_time_s": r.total_time_s,
        "segments": [
            {"from_id": s.from_id, "to_id": s.to_id, "edge_type": s.edge_type,
             "distance_meter": s.distance_meter, "time_s": s.time_s}
            for s in r.segments
        ],
    }
