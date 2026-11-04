"""平面坐标下的空间计算（SVG 网格坐标系，与 M3/M4 同口径）。"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable


def distance_2d(a: tuple[float, float], b: tuple[float, float]) -> float:
    """欧氏距离（SVG 单位；米数由调用方乘 scale）。"""
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def sort_nearest(
    items: Iterable[dict],
    position: tuple[float, float] | None,
    here_floor=None,
    floor_key: str = "floor_id",
    x_key: str = "x",
    y_key: str = "y",
    cross_floor_penalty: float = 1e9,
) -> list[dict]:
    """按平面距离排序；同层优先（跨层加惩罚仍参与列表）；无位置时保原序。

    纯函数：返回新列表，不改动输入；跨层惩罚由调用方给值（策略不内置）。
    """
    if position is None:
        return list(items)
    fx, fy = position

    def dist(it: dict) -> float:
        if it.get(x_key) is None or it.get(floor_key) is None:
            return cross_floor_penalty
        plane = distance_2d((float(it[x_key]), float(it[y_key])), (fx, fy))
        return plane + (0.0 if it[floor_key] == here_floor else cross_floor_penalty)

    return sorted(items, key=dist)


def connected_components(
    nodes: Iterable[tuple[int, float, float]],
    edges: Iterable[tuple[int, int]],
) -> list[set[int]]:
    """路网连通分量（scene_check 孤岛检测用）。nodes=[(id,x,y)]，edges=[(a,b)]。"""
    adj: dict[int, set[int]] = {n[0]: set() for n in nodes}
    for a, b in edges:
        if a in adj and b in adj:
            adj[a].add(b)
            adj[b].add(a)
    seen: set[int] = set()
    out: list[set[int]] = []
    for n in adj:
        if n in seen:
            continue
        comp: set[int] = set()
        queue = deque([n])
        seen.add(n)
        while queue:
            cur = queue.popleft()
            comp.add(cur)
            for nb in adj[cur]:
                if nb not in seen:
                    seen.add(nb)
                    queue.append(nb)
        out.append(comp)
    return out
