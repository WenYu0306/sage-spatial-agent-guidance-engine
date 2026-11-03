"""跨层路线示例运行：python -m route_engine.demo <起点POI> <终点POI>。

从库加载路网（DATABASE_URL），POI 名称解析成节点，A* 规划并打印分段/距离/耗时。
"""

from __future__ import annotations

import sys

import psycopg

from .db import _dsn, load_route_graph
from .graph import RouteError, build_graph, plan

TENANT_CODE = "shanqueli-demo"
VENUE_NAME = "山雀里·栖云广场"


def _venue_id(cur) -> int:
    cur.execute(
        "select v.id from venues v join tenants t on t.id = v.tenant_id "
        "where t.code = %s and v.name = %s",
        (TENANT_CODE, VENUE_NAME),
    )
    row = cur.fetchone()
    if not row:
        raise SystemExit(f"未找到场地 {TENANT_CODE}/{VENUE_NAME}")
    return row[0]


def _resolve_poi_node(cur, venue_id: int, name: str) -> int:
    cur.execute(
        "select n.id from pois p join route_nodes n on n.poi_id = p.id "
        "where p.venue_id = %s and p.name = %s",
        (venue_id, name),
        )
    row = cur.fetchone()
    if not row:
        raise SystemExit(f"POI 未接入路网：{name}")
    return row[0]


def _node_label(cur, node_id: int) -> str:
    cur.execute(
        "select coalesce(p.name, '走廊点(' || rn.x::text || ',' || rn.y::text || ')'), "
        "f.name from route_nodes rn "
        "join floors f on f.id = rn.floor_id "
        "left join pois p on p.id = rn.poi_id "
        "where rn.id = %s",
        (node_id,),
    )
    label, floor_name = cur.fetchone()
    return f"{label}({floor_name})"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("用法：python -m route_engine.demo <起点POI名> <终点POI名>", file=sys.stderr)
        return 2
    start_name, goal_name = argv
    nodes, edges, scale = load_route_graph(TENANT_CODE, VENUE_NAME)
    g = build_graph(nodes, edges, scale_meter=scale)
    with psycopg.connect(_dsn()) as conn, conn.cursor() as cur:
        venue = _venue_id(cur)
        start_id = _resolve_poi_node(cur, venue, start_name)
        goal_id = _resolve_poi_node(cur, venue, goal_name)
        try:
            result = plan(g, start_id, goal_id, scale_meter=scale)
        except RouteError as exc:
            print(f"路线失败 code={exc.code}：{exc}")
            return 1
        print(f"路线：{start_name} → {goal_name}")
        for i, seg in enumerate(result.segments, 1):
            print(
                f"  {i}. [{seg.edge_type:<9}] "
                f"{_node_label(cur, seg.from_id)} → {_node_label(cur, seg.to_id)}  "
                f"{seg.distance_meter:.1f}m  {seg.time_s:.1f}s"
            )
        m, s = result.total_distance_meter, result.total_time_s
        mins, secs = int(s // 60), s % 60
        print(f"合计：{m:.1f} 米 / {s:.1f} 秒（约 {mins} 分 {secs:.0f} 秒，含垂直交通惩罚）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
