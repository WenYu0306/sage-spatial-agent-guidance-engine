"""M2 场景导入器（D-029 换场景验收）：mall_navigation_v1 → 新场地。

从画图 agent 交付包（GeoJSON + network JSON）构建完整场地：
- 楼层 B1/F1/F2 + 米制 map_layers（scale=1.0，viewBox=建筑外框 330×270）
- 路网：~2,207 节点 / ~2,881 walk 边（door 节点已在包内映射店铺）
- 跨层边：扶梯 8 组三层同位（escalator，非无障碍）、客梯 4 组（elevator，无障碍）
- POI 重映射（A 方案）：锚店对位，演示店名分配到铺位质心，绑定 door 节点，
  简介按 seed 模板生成（知识检索可用）

幂等：整场子表清空重建（场地行保留），验收期可反复执行。
用法：uv run python -m deploy.seed.import_mall_scene [--pkg <包路径>]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import psycopg
import yaml
from psycopg.types.json import Jsonb

TENANT_CODE = "shanqueli-demo"
VENUE_NAME = "栖云广场·云枢 mall"
FLOORS = (("B1", -1), ("F1", 1), ("F2", 2))
FILE_KEY = {"B1": "B1", "F1": "F1_v5", "F2": "F2"}
ANCHORS = {  # 演示名 → (层, kind)
    "云雀优选超市": ("B1", "supermarket"),
    "巨幕星云影院": ("F2", "anchor_store"),
    "云上乐园": ("F2", "anchor_store"),
    "潮汐健身": ("F2", "anchor_store"),
}
ANCHOR_CATEGORY = {"云雀优选超市": "supermarket", "巨幕星云影院": "cinema",
                   "云上乐园": "kids_play", "潮汐健身": "gym"}
SCENE_TABLES = ("coupon_claims", "coupons", "route_edges", "route_nodes",
                "activities", "pois", "map_layers", "floors")
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _load_env() -> None:
    env = Path(__file__).resolve().parents[2] / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip().strip("'\""))


def _centroid(feature) -> tuple[float, float]:
    ring = feature["geometry"]["coordinates"][0]
    return (sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring))


def _spread(features: list[dict], count: int) -> list[dict]:
    """按质心排序后等距取样（铺满动线），count 超出时全取。"""
    ordered = sorted(features, key=lambda f: (_centroid(f)[1], _centroid(f)[0]))
    if len(ordered) <= count:
        return ordered
    step = len(ordered) / count
    return [ordered[int(i * step)] for i in range(count)]


def _demo_shop_names() -> dict[str, list[dict]]:
    """演示店名按目标层分组（保留名字/标签/热度/知识库与评测体系）。"""
    out: dict[str, list[dict]] = defaultdict(list)
    data = Path(__file__).resolve().parent / "data"
    for f, floor in (("pois_b1.yaml", "F1"), ("pois_f1.yaml", "F1"),
                     ("pois_f2.yaml", "F2")):
        for p in yaml.safe_load((data / f).read_text(encoding="utf-8"))["pois"]:
            out[floor].append(p)
    return out


def main() -> int:
    _load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--pkg", default="/Users/wenyudemac/Documents/dev/SAGE-Spatial Agent Guidance Engine/mall_navigation_v1")
    ap.add_argument("--dsn", default=None)
    args = ap.parse_args()
    dsn = (args.dsn or os.environ.get("DATABASE_URL", "")).replace(
        "postgresql+psycopg://", "postgresql://", 1)
    pkg = Path(args.pkg)

    scene: dict[str, dict] = {}
    for fl, _ in FLOORS:
        key = FILE_KEY[fl]
        scene[fl] = {
            "gj": json.loads((pkg / "out" / f"{key}.geojson").read_text(encoding="utf-8")),
            "nw": json.loads((pkg / "out" / f"{key}_network.json").read_text(encoding="utf-8")),
        }

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("select id from tenants where code=%s", (TENANT_CODE,))
        tid = cur.fetchone()[0]

        # 1) 场地（保留行；子表清空重建，验收期可反复执行）
        cur.execute("select id from venues where tenant_id=%s and name=%s",
                    (tid, VENUE_NAME))
        row = cur.fetchone()
        if row:
            vid = row[0]
            for table in SCENE_TABLES:
                cur.execute(f"delete from {table} where venue_id=%s", (vid,))
        else:
            vid = cur.execute(
                "insert into venues (tenant_id, name, venue_type, address, timezone, "
                "status) values (%s, %s, 'mall', '虚构市云枢区（米制场景包）', "
                "'Asia/Shanghai', 'active') returning id", (tid, VENUE_NAME)).fetchone()[0]

        # 2) 楼层 + 米制 map_layers（前端 viewBox 从这里读）
        floor_ids: dict[str, int] = {}
        for sort_order, (fl, level) in enumerate(FLOORS):
            floor_ids[fl] = cur.execute(
                "insert into floors (tenant_id, venue_id, name, level, sort_order) "
                "values (%s, %s, %s, %s, %s) returning id",
                (tid, vid, fl, level, sort_order)).fetchone()[0]
        for fl, _ in FLOORS:
            cur.execute(
                "insert into map_layers (tenant_id, venue_id, floor_id, version, svg_url, "
                "width, height, scale_meter) values (%s, %s, %s, 1, %s, 330, 270, 1.0)",
                (tid, vid, floor_ids[fl], f"/static/maps/{fl.lower()}.svg"))
        print(f"场地 {VENUE_NAME} (id={vid})：楼层+图层就绪")

        # 3) 路网（waypoint + 扶梯/电梯 kind 节点）与 walk 边
        node_ids: dict[str, dict[str, int]] = {}
        for fl, _ in FLOORS:
            fid = floor_ids[fl]
            node_ids[fl] = {}
            for code, (x, y) in scene[fl]["nw"]["nodes"].items():
                node_ids[fl][code] = cur.execute(
                    "insert into route_nodes (tenant_id, venue_id, floor_id, node_type, "
                    "x, y, accessible) values (%s, %s, %s, 'waypoint', %s, %s, true) "
                    "returning id", (tid, vid, fid, x, y)).fetchone()[0]
            for ft in scene[fl]["gj"]["features"]:
                kind = ft["properties"].get("kind")
                if kind in ("escalator", "elevator"):
                    (x, y) = ft["geometry"]["coordinates"]
                    node_ids[fl][f"{kind}@{x}:{y}"] = cur.execute(
                        "insert into route_nodes (tenant_id, venue_id, floor_id, "
                        "node_type, x, y, accessible) "
                        "values (%s, %s, %s, %s, %s, %s, %s) returning id",
                        (tid, vid, fid, kind, x, y,
                         kind == "elevator")).fetchone()[0]
            for a, b, dist in scene[fl]["nw"]["edges"]:
                na, nb = node_ids[fl].get(str(a)), node_ids[fl].get(str(b))
                if na is None or nb is None:
                    continue
                cur.execute(
                    "select 1 from route_edges where venue_id=%s and from_node_id=%s "
                    "and to_node_id=%s and edge_type='walk'", (vid, na, nb))
                if cur.fetchone():
                    continue
                cur.execute(
                    "insert into route_edges (tenant_id, venue_id, from_node_id, "
                    "to_node_id, edge_type, distance_meter, weight, accessible, "
                    "is_bidirectional) values (%s, %s, %s, %s, 'walk', %s, %s, "
                    "true, true)",
                    (tid, vid, na, nb, dist, dist / 1.2))
            conn.commit()
            print(f"{fl} 路网就绪")

        # 4) 跨层边：扶梯/电梯三层同位（坐标即配对键）
        made = 0
        for kind in ("escalator", "elevator"):
            for lo, hi in (("B1", "F1"), ("F1", "F2")):
                for key, a in node_ids[lo].items():
                    if not key.startswith(f"{kind}@"):
                        continue
                    b = node_ids[hi].get(key)
                    if b is None:
                        continue
                    cur.execute(
                        "insert into route_edges (tenant_id, venue_id, from_node_id, "
                        "to_node_id, edge_type, distance_meter, weight, accessible, "
                        "is_bidirectional) values (%s, %s, %s, %s, %s, 5.2, "
                        "case when %s = 'elevator' then 40.0 else 30.0 end, %s, true)",
                        (tid, vid, a, b, kind, kind, kind == "elevator"))
                    made += 1
            conn.commit()
        print(f"跨层边就绪（{made} 条）")

        # 5) POI 重映射（A 方案）
        cats = yaml.safe_load(
            (Path(__file__).resolve().parent / "data/poi_categories.yaml")
            .read_text(encoding="utf-8"))["categories"]
        cat_name = {c["code"]: c["name"] for c in cats}
        hours = Jsonb({d: ["10:00-22:00"] for d in DAYS} | {"holidays": []})
        poi_ids: dict[str, int] = {}

        def mk_poi(floor: str, name: str, category: str, x: float, y: float,
                   tags: list[str] | None = None, hot: float = 60.0,
                   door_node: int | None = None) -> int:
            pid = cur.execute(
                "insert into pois (tenant_id, venue_id, floor_id, category_code, name, "
                "status, position_x, position_y, business_hours, tags, hot_score) "
                "values (%s, %s, %s, %s, %s, 'published', %s, %s, %s, %s, %s) "
                "returning id",
                (tid, vid, floor_ids[floor], category, name, x, y, hours,
                 Jsonb(tags or []), hot)).fetchone()[0]
            poi_ids[name] = pid
            if door_node is not None:
                cur.execute("update route_nodes set poi_id=%s where id=%s",
                            (pid, door_node))
            return pid

        # 锚店：对位到同 kind 最大多边形质心
        for name, (fl, kind) in ANCHORS.items():
            cands = [ft for ft in scene[fl]["gj"]["features"]
                     if ft["properties"].get("kind") == kind]
            if not cands:
                continue
            big = max(cands, key=lambda ft: len(ft["geometry"]["coordinates"][0]))
            x, y = _centroid(big)
            mk_poi(fl, name, ANCHOR_CATEGORY[name], x, y, tags=[kind], hot=90.0)
        conn.commit()
        print("锚店就绪")

        # 演示店分配：B1+F1 店名→F1 铺位；F2 店名→F2 铺位
        names = _demo_shop_names()
        f1_polys = [ft for ft in scene["F1"]["gj"]["features"]
                    if ft["properties"].get("kind") == "shop"]
        f2_polys = [ft for ft in scene["F2"]["gj"]["features"]
                    if ft["properties"].get("kind") == "shop"]
        f1_pick = _spread(f1_polys, len(names["F1"]) + len(names["B1"]))
        f2_pick = _spread(f2_polys, len(names["F2"]))
        door_f1 = scene["F1"]["nw"]["shop_door_node"]
        door_f2 = scene["F2"]["nw"]["shop_door_node"]

        for i, p in enumerate(names["F1"] + names["B1"]):
            ft = f1_pick[i]
            x, y = _centroid(ft)
            door = node_ids["F1"].get(str(door_f1.get(ft["properties"]["code"], "")))
            if p["name"] in poi_ids:
                continue
            mk_poi("F1", p["name"], p["category"], x, y, tags=p.get("tags"),
                   hot=p.get("hot", 60.0), door_node=door)
        for i, p in enumerate(names["F2"]):
            ft = f2_pick[i]
            x, y = _centroid(ft)
            door = node_ids["F2"].get(str(door_f2.get(ft["properties"]["code"], "")))
            if p["name"] in poi_ids:
                continue
            mk_poi("F2", p["name"], p["category"], x, y, tags=p.get("tags"),
                   hot=p.get("hot", 60.0), door_node=door)
        conn.commit()
        print(f"POI 重映射就绪（{len(poi_ids)} 家）")

        # 6) 简介（知识检索可用，模式沿 seed）
        for name, pid in poi_ids.items():
            cur.execute("select floor_id, category_code from pois where id=%s", (pid,))
            pfid, cat = cur.fetchone()
            cur.execute("select name from floors where id=%s", (pfid,))
            fname = cur.fetchone()[0]
            cur.execute(
                "insert into knowledge_documents (tenant_id, venue_id, poi_id, doc_type, "
                "title, content, status) values (%s, %s, %s, 'poi_intro', %s, %s, 'active')",
                (tid, vid, pid, f"{name}·店铺介绍",
                 f"{name}位于栖云广场{fname}层，属于{cat_name.get(cat, cat)}业态。"
                 "以上信息由商场运营方维护。"))
        conn.commit()

        cur.execute("select count(*) from pois where venue_id=%s", (vid,))
        n_poi = cur.fetchone()[0]
        cur.execute("select count(*) from route_nodes where venue_id=%s", (vid,))
        n_node = cur.fetchone()[0]
        cur.execute("select count(*) from route_edges where venue_id=%s", (vid,))
        n_edge = cur.fetchone()[0]
    print(f"导入完成：POI {n_poi} | 路网 {n_node} 节点 / {n_edge} 边")
    return 0


if __name__ == "__main__":
    sys.exit(main())
