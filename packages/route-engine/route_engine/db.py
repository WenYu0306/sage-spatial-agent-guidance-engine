"""从库加载路网（deploy/seed 产出的 route_nodes/route_edges 是唯一数据源）。"""

from __future__ import annotations

import os

import psycopg

from .graph import EdgeRow, NodeRow


def _dsn() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise SystemExit("DATABASE_URL 未设置：复制 .env.example 为 .env")
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def load_route_graph(tenant_code: str, venue_name: str):
    """按租户编码+场地名加载节点/边/比例尺。"""
    with psycopg.connect(_dsn()) as conn, conn.cursor() as cur:
        cur.execute(
            "select v.id, v.tenant_id from venues v "
            "join tenants t on t.id = v.tenant_id "
            "where t.code = %s and v.name = %s",
            (tenant_code, venue_name),
        )
        row = cur.fetchone()
        if not row:
            raise SystemExit(f"未找到场地 {tenant_code}/{venue_name}")
        venue_id, _tenant_id = row

        cur.execute(
            "select id, floor_id, node_type, poi_id, x, y, accessible "
            "from route_nodes where venue_id = %s",
            (venue_id,),
        )
        nodes = {
            r[0]: NodeRow(r[0], r[1], float(r[4]), float(r[5]), r[2], r[6], r[3])
            for r in cur.fetchall()
        }
        cur.execute(
            "select from_node_id, to_node_id, edge_type, distance_meter, weight, "
            "accessible, is_bidirectional from route_edges where venue_id = %s",
            (venue_id,),
        )
        edges = [EdgeRow(*r[:3], float(r[3]), float(r[4]), r[5], r[6])
                 for r in cur.fetchall()]
        cur.execute(
            "select ml.scale_meter from map_layers ml "
            "join floors f on f.id = ml.floor_id "
            "where ml.venue_id = %s and f.level = 1",
            (venue_id,),
        )
        scale = float(cur.fetchone()[0])
    return nodes, edges, scale
