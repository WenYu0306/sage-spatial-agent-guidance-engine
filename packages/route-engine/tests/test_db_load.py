"""M3 integration tests: load the real seeded graph and plan across 3 floors.

Requires DATABASE_URL and `make seed`. Covers task output 1:
B1 supermarket -> F2 cinema cross-floor route example.
"""

from __future__ import annotations

import psycopg
import pytest
from route_engine.db import load_route_graph
from route_engine.graph import build_graph, plan


@pytest.fixture(scope="module")
def bundle():
    nodes, edges, scale = load_route_graph("shanqueli-demo", "山雀里·栖云广场")
    return nodes, edges, scale


def test_loaded_graph_scale(bundle):
    nodes, edges, _ = bundle
    assert (len(nodes), len(edges)) == (106, 224)


def test_plan_b1_supermarket_to_f2_cinema(bundle, seed_mod):
    nodes, edges, scale = bundle
    g = build_graph(nodes, edges, scale_meter=scale)
    poi_nodes = {v.poi_id: k for k, v in nodes.items() if v.poi_id}

    with psycopg.connect(seed_mod._dsn()) as conn, conn.cursor() as cur:
        cur.execute(
            "select name, id from pois where name in ('云雀优选超市', '巨幕星云影院')"
        )
        ids = dict(cur.fetchall())
    start = poi_nodes[ids["云雀优选超市"]]
    goal = poi_nodes[ids["巨幕星云影院"]]
    r = plan(g, start, goal, scale_meter=scale)
    assert r.total_distance_meter > 0 and r.total_time_s > 0
    assert len(r.segments) >= 8, "cross-floor route segments"
    assert "elevator" in [s.edge_type for s in r.segments], "should pass an elevator"
