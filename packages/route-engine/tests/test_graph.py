"""M3 规划引擎单测（纯函数核，不连库）：A* 路径、权重合计、无障碍过滤、2003/2004。

合成路网：F1 有 wp1/wp2/POI3/电梯4 与楼梯 wp8；F2 有电梯5/wp6/POI7。
跨层唯一无障碍通道是电梯（4↔5）；6→5 只有下行扶梯（非无障碍、单向）。
"""

from __future__ import annotations

import networkx as nx
import pytest
from route_engine.graph import EdgeRow, NodeRow, RouteError, build_graph, plan

SCALE = 0.15

NODES = {
    1: NodeRow(1, 1, 150.0, 260.0, "waypoint", True),
    2: NodeRow(2, 1, 600.0, 260.0, "waypoint", True),
    3: NodeRow(3, 1, 990.0, 180.0, "poi_link", True, poi_id=101),
    4: NodeRow(4, 1, 600.0, 200.0, "elevator", True),
    5: NodeRow(5, 2, 600.0, 200.0, "elevator", True),
    6: NodeRow(6, 2, 600.0, 260.0, "waypoint", True),
    7: NodeRow(7, 2, 850.0, 130.0, "poi_link", True, poi_id=202),
    8: NodeRow(8, 1, 150.0, 560.0, "waypoint", True),
}

EDGES = [
    EdgeRow(1, 2, "walk", 67.5, 56.25, True, True),
    EdgeRow(3, 1, "walk", 100.0, 83.333, True, True),
    EdgeRow(2, 4, "walk", 9.0, 7.5, True, True),
    EdgeRow(4, 5, "elevator", 5.2, 60.0, True, True),
    EdgeRow(6, 7, "walk", 56.25, 46.875, True, True),
    EdgeRow(5, 6, "walk", 9.0, 7.5, True, True),
    EdgeRow(1, 8, "stairs", 45.0, 90.0, False, True),
    EdgeRow(6, 5, "escalator", 5.2, 40.0, False, False),
]

ISOLATED = {**NODES, 9: NodeRow(9, 3, 600.0, 260.0, "waypoint", True)}


def test_plan_cross_floor_via_elevator():
    g = build_graph(NODES, EDGES, scale_meter=SCALE)
    r = plan(g, 3, 7, scale_meter=SCALE)
    assert [s.edge_type for s in r.segments] == [
        "walk", "walk", "walk", "elevator", "walk", "walk",
    ]
    assert r.total_distance_meter == pytest.approx(246.95, abs=0.01)
    expect_t = 83.333 + 56.25 + 7.5 + 60.0 + 7.5 + 46.875
    assert r.total_time_s == pytest.approx(expect_t, abs=0.01)
    assert r.node_path[0] == 3 and r.node_path[-1] == 7


def test_reverse_traversal_uses_bidirectional_edges():
    g = build_graph(NODES, EDGES, scale_meter=SCALE)
    r = plan(g, 7, 3, scale_meter=SCALE)
    types = [s.edge_type for s in r.segments]
    assert "elevator" in types and "escalator" in types


def test_accessible_mode_blocks_escalator_only_link():
    """无障碍模式剔除扶梯/楼梯：扶梯是唯一跨层通道时，无障碍规划必须 2003。"""
    g2_nodes = {
        1: NodeRow(1, 1, 0.0, 0.0, "waypoint", True),
        2: NodeRow(2, 1, 67.5, 0.0, "elevator", True),   # 名为电梯实为 F1 侧节点
        3: NodeRow(3, 2, 67.5, 0.0, "elevator", True),   # F2 侧节点
        4: NodeRow(4, 2, 135.0, 0.0, "waypoint", True),
    }
    g2_edges = [
        EdgeRow(1, 2, "walk", 10.0, 8.33, True, True),
        EdgeRow(3, 4, "walk", 10.0, 8.33, True, True),
        EdgeRow(2, 3, "escalator", 5.2, 40.0, False, False),
    ]
    g = build_graph(g2_nodes, g2_edges, scale_meter=SCALE)
    r = plan(g, 1, 4, scale_meter=SCALE)
    assert "escalator" in [s.edge_type for s in r.segments]
    with pytest.raises(RouteError) as ei:
        plan(build_graph(g2_nodes, g2_edges, scale_meter=SCALE, accessible_only=True),
             1, 4, scale_meter=SCALE)
    assert ei.value.code == 2003
    with pytest.raises(RouteError) as ei2:
        plan(g, 4, 1, scale_meter=SCALE)  # 扶梯单向（上行），反向不可达
    assert ei2.value.code == 2003


def test_unreachable_raises_2003():
    g = build_graph(ISOLATED, EDGES, scale_meter=SCALE)
    with pytest.raises(RouteError) as ei:
        plan(g, 3, 9, scale_meter=SCALE)
    assert ei.value.code == 2003


def test_empty_graph_raises_2004():
    with pytest.raises(RouteError) as ei:
        build_graph({}, [], scale_meter=SCALE)
    assert ei.value.code == 2004


def test_astar_equals_dijkstra():
    g = build_graph(NODES, EDGES, scale_meter=SCALE)
    goal = g.nodes[7]

    def h(u, v):  # noqa: ARG001
        dx = g.nodes[u]["x"] - goal["x"]
        dy = g.nodes[u]["y"] - goal["y"]
        return ((dx * dx + dy * dy) ** 0.5) * SCALE / 1.2

    a = nx.astar_path(g, 3, 7, heuristic=h, weight="weight")
    d = nx.dijkstra_path(g, 3, 7, weight="weight")
    assert a == d


def test_segment_sums_match_totals():
    g = build_graph(NODES, EDGES, scale_meter=SCALE)
    r = plan(g, 3, 7, scale_meter=SCALE)
    assert sum(s.distance_meter for s in r.segments) == pytest.approx(
        r.total_distance_meter, abs=0.01,
    )
    assert sum(s.time_s for s in r.segments) == pytest.approx(r.total_time_s, abs=0.01)
