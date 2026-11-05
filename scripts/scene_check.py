#!/usr/bin/env python3
"""换场景数据体检（D-029 配套，ASSUMPTIONS A14）：新场地导入后跑一遍，八项检查。

检查项：楼层图层齐全 / POI 坐标在图层内 / 分类已发布 / door 绑定率 /
路网连通（孤岛检测，复用 spatial_model）/ 相邻层跨层边 / 无障碍边 /
知识简介覆盖。任一 FAIL 退出码 1。

用法：uv run python scripts/scene_check.py --tenant shanqueli-demo --venue "栖云广场·云枢 mall"
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg
from spatial_model.geometry import connected_components

VERTICAL = ("escalator", "elevator")


def _load_env() -> None:
    env = Path(__file__).resolve().parents[1] / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip().strip("'\""))


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []

    def add(self, state: str, name: str, detail: str) -> None:
        self.rows.append((state, name, detail))
        mark = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗"}[state]
        print(f"  {mark} {state:<4} {name}：{detail}")

    @property
    def failed(self) -> bool:
        return any(s == "FAIL" for s, _, _ in self.rows)


def main() -> int:
    _load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", default="shanqueli-demo")
    ap.add_argument("--venue", required=True)
    ap.add_argument("--dsn", default=None)
    args = ap.parse_args()
    dsn = (args.dsn or os.environ.get("DATABASE_URL", "")).replace(
        "postgresql+psycopg://", "postgresql://", 1)

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "select v.id from venues v join tenants t on t.id=v.tenant_id "
            "where t.code=%s and v.name=%s", (args.tenant, args.venue))
        row = cur.fetchone()
        if not row:
            print(f"✗ 找不到场地：tenant={args.tenant} venue={args.venue}")
            return 1
        vid = row[0]
        print(f"体检场地 {args.venue} (id={vid})")

        rep = Report()

        # ① 楼层与图层
        cur.execute(
            "select f.id, f.name, f.level, m.width, m.height from floors f "
            "left join map_layers m on m.floor_id=f.id "
            "where f.venue_id=%s order by f.level", (vid,))
        floors = cur.fetchall()
        no_layer = [f[1] for f in floors if f[3] is None]
        if not floors:
            rep.add("FAIL", "楼层", "场地无楼层")
        elif no_layer:
            rep.add("FAIL", "楼层图层", f"{len(no_layer)} 层缺 map_layer：{no_layer}")
        else:
            rep.add("PASS", "楼层图层", f"{len(floors)} 层齐全")
        layer_by_floor = {f[0]: f for f in floors if f[3] is not None}

        # ②③ POI 坐标与发布状态
        cur.execute(
            "select p.name, p.status, p.position_x, p.position_y, p.floor_id "
            "from pois p where p.venue_id=%s and p.deleted_at is null", (vid,))
        pois = cur.fetchall()
        if not pois:
            rep.add("FAIL", "POI", "场地无 POI")
        else:
            out_of_bounds = [
                name for name, _st, x, y, pfid in pois
                if pfid in layer_by_floor
                and not (0 <= float(x) <= float(layer_by_floor[pfid][3])
                         and 0 <= float(y) <= float(layer_by_floor[pfid][4]))]
            if out_of_bounds:
                rep.add("FAIL", "POI 坐标",
                        f"{len(out_of_bounds)} 个越界：{out_of_bounds[:5]}")
            else:
                rep.add("PASS", "POI 坐标", f"{len(pois)} 个全部在图层 bbox 内")
            published = sum(1 for p in pois if p[1] == "published")
            if published == 0:
                rep.add("FAIL", "POI 发布", "无 published POI")
            else:
                rep.add("PASS", "POI 发布", f"{published}/{len(pois)} published")

        # ④ door 节点绑定率（低于 50% 才 WARN；锚店/设施可不绑）
        cur.execute(
            "select count(*) from route_nodes where venue_id=%s and poi_id is not null",
            (vid,))
        bound = cur.fetchone()[0]
        ratio = bound / len(pois) if pois else 0
        if ratio < 0.5:
            rep.add("WARN", "door 绑定", f"仅 {bound}/{len(pois)} POI 绑定路网节点")
        else:
            rep.add("PASS", "door 绑定", f"{bound}/{len(pois)} POI 绑定路网节点")

        # ⑤ 路网连通（spatial_model 孤岛检测）
        cur.execute(
            "select id, x, y from route_nodes where venue_id=%s", (vid,))
        nodes = [(r[0], float(r[1]), float(r[2])) for r in cur.fetchall()]
        cur.execute(
            "select from_node_id, to_node_id from route_edges where venue_id=%s", (vid,))
        edges = [(r[0], r[1]) for r in cur.fetchall()]
        comps = connected_components(nodes, edges)
        comps.sort(key=len, reverse=True)
        if not nodes:
            rep.add("FAIL", "路网", "无路网节点")
        elif len(comps) == 1:
            rep.add("PASS", "路网连通", f"{len(nodes)} 节点全连通")
        else:
            share = len(comps[0]) / len(nodes)
            state = "PASS" if share >= 0.98 else "FAIL"
            rep.add(state, "路网连通",
                    f"{len(comps)} 个分量，最大占 {share:.0%}"
                    f"（孤岛规模：{[len(c) for c in comps[1:6]]}…）")

        # ⑥ 相邻层跨层边
        levels = sorted(floors, key=lambda f: f[2])
        gaps = []
        for lo, hi in zip(levels, levels[1:]):
            cur.execute(
                "select count(*) from route_edges e "
                "join route_nodes a on a.id=e.from_node_id "
                "join route_nodes b on b.id=e.to_node_id "
                "where e.venue_id=%s and a.floor_id=%s and b.floor_id=%s "
                "and e.edge_type = ANY(%s)",
                (vid, lo[0], hi[0], list(VERTICAL)))
            if cur.fetchone()[0] == 0:
                gaps.append(f"{lo[1]}↔{hi[1]}")
        if gaps:
            rep.add("FAIL", "跨层边", f"相邻层无扶梯/电梯边：{gaps}")
        else:
            rep.add("PASS", "跨层边", f"{len(levels) - 1} 组相邻层均有垂直边")

        # ⑦ 无障碍垂直边
        cur.execute(
            "select count(*) from route_edges where venue_id=%s "
            "and accessible=true and edge_type = ANY(%s)", (vid, list(VERTICAL)))
        acc = cur.fetchone()[0]
        if acc == 0:
            rep.add("FAIL", "无障碍", "无 accessible 垂直边（轮椅动线不可用）")
        else:
            rep.add("PASS", "无障碍", f"{acc} 条无障碍垂直边")

        # ⑧ 知识简介覆盖
        cur.execute(
            "select count(*) from pois p where p.venue_id=%s and p.deleted_at is null "
            "and not exists (select 1 from knowledge_documents d "
            "where d.poi_id=p.id and d.status='active')", (vid,))
        missing = cur.fetchone()[0]
        if pois and missing > len(pois) * 0.2:
            rep.add("WARN", "知识简介",
                    f"{missing}/{len(pois)} POI 缺简介（知识检索覆盖不足）")
        else:
            rep.add("PASS", "知识简介", f"缺简介仅 {missing}/{len(pois)}")

    print(f"\n体检结论：{'FAIL（存在阻断项）' if rep.failed else 'PASS'}")
    return 1 if rep.failed else 0


if __name__ == "__main__":
    sys.exit(main())
