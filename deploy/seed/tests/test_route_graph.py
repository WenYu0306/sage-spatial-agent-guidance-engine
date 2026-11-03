"""路网 seed 验收：全图连通、无障碍子图跨层可达、PRD 6.3 权重规则、拓扑规模。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import psycopg
import pytest

SEED_PY = Path(__file__).resolve().parents[1] / "seed.py"


@pytest.fixture(scope="module")
def seed_mod():
    spec = importlib.util.spec_from_file_location("sage_seed", SEED_PY)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def graph(seed_mod):
    seed_mod.run_seed()
    with psycopg.connect(seed_mod._dsn()) as conn, conn.cursor() as cur:
        cur.execute("select id, floor_id, node_type, poi_id, accessible, x, y from route_nodes")
        nodes = {r[0]: {"floor": r[1], "type": r[2], "poi": r[3], "acc": r[4],
                        "x": float(r[5]), "y": float(r[6])}
                 for r in cur.fetchall()}
        cur.execute(
            "select from_node_id, to_node_id, edge_type, weight, accessible, "
            "is_bidirectional, distance_meter from route_edges"
        )
        edges = cur.fetchall()
        cur.execute("select id, name from floors")
        floor_names = dict(cur.fetchall())
    return nodes, edges, floor_names


def test_graph_scale(graph):
    nodes, edges, _ = graph
    # 节点 106 = 18 走廊 + 88 POI/设施（含 7 垂直交通节点）。
    # 边行 224 = 走廊 21 无向×2 + 接入 88 无向×2（含垂直节点接入）
    #          + 电梯 2 对×2 方向 + 扶梯 2 部×单向 1 行。
    assert len(nodes) == 106, f"节点数 {len(nodes)} 应为 106"
    assert len(edges) == 224, f"边行数 {len(edges)} 应为 224（拓扑变化须人工确认）"


def test_full_graph_connected(graph):
    nodes, edges, _ = graph
    start = next(iter(nodes))
    seen = _bfs(edges, start)
    assert seen == set(nodes), f"图不连通：{len(set(nodes) - seen)} 个节点不可达"


def test_accessible_subgraph_reaches_all(graph):
    nodes, edges, floor_names = graph
    start = next(n for n, v in nodes.items() if v["type"] == "poi_link")
    seen = _bfs(edges, start, accessible_only=True)
    levels = {floor_names[nodes[n]["floor"]] for n in seen}
    assert levels == {"B1", "F1", "F2"}, f"无障碍子图应覆盖 3 层，实际 {levels}"
    unreachable = set(nodes) - seen
    assert not unreachable, f"无障碍模式下 {len(unreachable)} 个节点不可达（扶梯不得为必经）"


def test_weight_rules(graph):
    _nodes, edges, _ = graph
    for f, t, et, w, acc, bi, d in edges:
        if et == "walk":
            assert abs(float(w) - round(float(d) / 1.2, 3)) < 1e-6, f"walk 权重≠距离/1.2：{f}->{t}"
        elif et == "elevator":
            assert float(w) == 60.0 and acc and bi, "电梯边应为 15+45s、无障碍、双向"
        elif et == "escalator":
            assert float(w) == 40.0 and not acc and not bi, "扶梯边应为 25+15s、非无障碍、单向"
        else:
            pytest.fail(f"未知边类型 {et}")


def test_escalator_direction(graph):
    """东（x 大）扶梯上行 F1→F2，西（x 小）扶梯下行 F2→F1。"""
    nodes, edges, floor_names = graph
    escalators = [(nodes[f]["x"], floor_names[nodes[f]["floor"]],
                   floor_names[nodes[t]["floor"]])
                  for f, t, et, *_r in edges if et == "escalator"]
    assert len(escalators) == 2, "应有东西两部扶梯各一条单向边"
    for x, f_floor, t_floor in escalators:
        if x >= 600:
            assert (f_floor, t_floor) == ("F1", "F2"), "东扶梯应上行 F1→F2"
        else:
            assert (f_floor, t_floor) == ("F2", "F1"), "西扶梯应下行 F2→F1"


def _bfs(edges, start, accessible_only=False):
    adj: dict[int, list[int]] = {}
    for f, t, _et, _w, acc, _bi, _d in edges:
        if accessible_only and not acc:
            continue
        adj.setdefault(f, []).append(t)
    seen, queue = {start}, [start]
    while queue:
        n = queue.pop()
        for m in adj.get(n, []):
            if m not in seen:
                seen.add(m)
                queue.append(m)
    return seen
