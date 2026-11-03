"""M3 路径规划核心（纯函数核）：networkx 建图 + A* + 无障碍过滤 + 2003/2004 错误码。

跨层边权重在 seed 阶段已按 PRD 6.3 预计算入库（含电梯 45s/扶梯 15s 惩罚），
引擎只读 weight 列；启发函数用直线距离/最高速度，可采纳（admissible）。
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx


class RouteError(Exception):
    """路径规划业务错误；code 对应 M0 错误码表（2003 不可达 / 2004 路网未构建）。"""

    def __init__(self, code: int, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True)
class NodeRow:
    id: int
    floor_id: int
    x: float
    y: float
    node_type: str
    accessible: bool
    poi_id: int | None = None


@dataclass(frozen=True)
class EdgeRow:
    from_id: int
    to_id: int
    edge_type: str
    distance_meter: float
    weight: float
    accessible: bool
    is_bidirectional: bool


@dataclass(frozen=True)
class Segment:
    from_id: int
    to_id: int
    edge_type: str
    distance_meter: float
    time_s: float


@dataclass(frozen=True)
class RouteResult:
    node_path: list[int]
    segments: list[Segment]
    total_distance_meter: float
    total_time_s: float


def build_graph(
    nodes: dict[int, NodeRow],
    edges: list[EdgeRow],
    *,
    scale_meter: float,
    accessible_only: bool = False,
) -> nx.DiGraph:
    """构建有向图；双向边写入两个方向。无障碍模式剔除不可达节点/边。"""
    if not nodes or not edges:
        raise RouteError(2004, "路网未构建")
    g: nx.DiGraph = nx.DiGraph()
    for n in nodes.values():
        if accessible_only and not n.accessible:
            continue
        g.add_node(n.id, x=n.x, y=n.y, floor_id=n.floor_id, node_type=n.node_type)
    for e in edges:
        if accessible_only and not e.accessible:
            continue
        if e.from_id not in g or e.to_id not in g:
            continue
        g.add_edge(e.from_id, e.to_id, edge_type=e.edge_type,
                   distance=e.distance_meter, weight=e.weight)
        if e.is_bidirectional:
            g.add_edge(e.to_id, e.from_id, edge_type=e.edge_type,
                       distance=e.distance_meter, weight=e.weight)
    if g.number_of_nodes() == 0:
        raise RouteError(2004, "过滤后路网为空")
    return g


def plan(
    g: nx.DiGraph, start_id: int, goal_id: int, *, scale_meter: float,
) -> RouteResult:
    """A* 求最短时间路径；不可达抛 2003。"""
    if start_id not in g or goal_id not in g:
        raise RouteError(2003, "起终点不在路网中")
    goal = g.nodes[goal_id]

    def h(u: int, v: int) -> float:  # noqa: ARG001 第二参数由 networkx 约定传入，此处不用
        dx = g.nodes[u]["x"] - goal["x"]
        dy = g.nodes[u]["y"] - goal["y"]
        return ((dx * dx + dy * dy) ** 0.5) * scale_meter / 1.2

    try:
        path = nx.astar_path(g, start_id, goal_id, heuristic=h, weight="weight")
    except nx.NetworkXNoPath:
        raise RouteError(2003, "起终点不可达") from None
    segments = [
        Segment(a, b, g.edges[a, b]["edge_type"],
                g.edges[a, b]["distance"], g.edges[a, b]["weight"])
        for a, b in zip(path, path[1:])
    ]
    return RouteResult(
        node_path=list(path),
        segments=segments,
        total_distance_meter=round(sum(s.distance_meter for s in segments), 2),
        total_time_s=round(sum(s.time_s for s in segments), 2),
    )
