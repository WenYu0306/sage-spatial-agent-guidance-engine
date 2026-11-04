"""底图网格校验（纯数据测试，不连库）：POI/设施坐标必须与真实商场动线一致。

规则（对应 scripts/gen_floor_maps.py 的绘制约定）：
1. 画布界内：40 <= x <= 1160, 40 <= y <= 760（1200x800 viewBox，留墙厚）。
2. 走廊净距：到 5 条走廊线段（y=260/560 横排 x150-1050；x=150/600/1050 纵排 y260-560）
   的距离 >= 58（走廊半宽 17 + 店面半高 36 + 余量 5），任何点位不得压在走廊上。
3. 环内店铺避让：环内（277<y<543）店铺 |x-600| >= 50（中庭南北通道），
   且到中庭圆心 (600,410) 距离 >= 135（中庭净空 r=85，店铺不贴脸）。
4. 设施贴中庭但不进净空：非服务台设施距中庭圆心 >= 95（净空外沿）；服务台 >= 45
   （真实商场服务台设在中庭南口/环边，但不压圆心）。
5. 同层任意两点间距 >= 46（点位徽标与店面不重叠）。
6. 垂直交通同位：电梯/扶梯在出现的各层 (x,y) 完全一致（seed 按 (category,x,y) 配对跨层）。
"""

from __future__ import annotations

from pathlib import Path

import yaml

DATA = Path(__file__).resolve().parent.parent / "data"
CORRIDOR_SEGS = [
    ((150.0, 260.0), (1050.0, 260.0)),
    ((150.0, 560.0), (1050.0, 560.0)),
    ((150.0, 260.0), (150.0, 560.0)),
    ((600.0, 260.0), (600.0, 560.0)),
    ((1050.0, 260.0), (1050.0, 560.0)),
]
ATRIUM = (600.0, 410.0)
ATRIUM_R = 85.0
FACILITY_CATS = {
    "toilet", "nursing_room", "elevator", "escalator",
    "info_desk", "parking", "atm", "charging_station", "clinic",
}


def _seg_dist(p, a, b) -> float:
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return ((px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2) ** 0.5


def _all_pois() -> list[dict]:
    rows: list[dict] = []
    for f in ("pois_b1.yaml", "pois_f1.yaml", "pois_f2.yaml", "facilities.yaml"):
        d = yaml.safe_load((DATA / f).read_text(encoding="utf-8"))
        for p in d["pois"]:
            rows.append({**p, "floor": p.get("floor", d.get("floor"))})
    return rows


def test_bounds_and_corridor_clearance():
    bad = []
    for p in _all_pois():
        x, y, name = float(p["x"]), float(p["y"]), p["name"]
        if not (40 <= x <= 1160 and 40 <= y <= 760):
            bad.append(f"{name} 越界 ({x},{y})")
        for a, b in CORRIDOR_SEGS:
            d = _seg_dist((x, y), a, b)
            if d < 58:
                bad.append(f"{name} 距走廊 {d:.0f}px < 58 ({x},{y})")
    assert not bad, "\n".join(bad)


def test_interior_avoids_passage_and_atrium():
    bad = []
    for p in _all_pois():
        x, y = float(p["x"]), float(p["y"])
        if not 277 < y < 543 or p["category"] in ("elevator", "escalator"):
            continue
        d_atrium = ((x - ATRIUM[0]) ** 2 + (y - ATRIUM[1]) ** 2) ** 0.5
        if p["category"] not in FACILITY_CATS:
            if abs(x - 600) < 50:
                bad.append(f"{p['name']} 骑中庭通道 (x={x})")
            if d_atrium < 135:
                bad.append(f"{p['name']} 距中庭 {d_atrium:.0f}px < 135")
        elif p["category"] == "info_desk":
            if d_atrium < 45:
                bad.append(f"{p['name']} 压中庭圆心 {d_atrium:.0f}px")
        elif d_atrium < ATRIUM_R + 10:
            bad.append(f"{p['name']} 侵入中庭净空 {d_atrium:.0f}px")
    assert not bad, "\n".join(bad)


def test_min_pairwise_spacing_per_floor():
    by_floor: dict[str, list[dict]] = {}
    for p in _all_pois():
        by_floor.setdefault(p["floor"], []).append(p)
    bad = []
    for floor, rows in by_floor.items():
        for i, a in enumerate(rows):
            for b in rows[i + 1 :]:
                d = ((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2) ** 0.5
                if d < 46:
                    bad.append(f"{floor} {a['name']}↔{b['name']} 间距 {d:.0f}px < 46")
    assert not bad, "\n".join(bad)


def test_vertical_transport_aligned_across_floors():
    pos: dict[tuple, set] = {}
    for p in _all_pois():
        if p["category"] in ("elevator", "escalator"):
            pos.setdefault((p["category"], float(p["x"]), float(p["y"])), set()).add(p["floor"])
    for (cat, x, y), floors in pos.items():
        assert len(floors) >= 2, f"{cat}@({x},{y}) 只出现在 {floors}，无法跨层配对"
    escalators = {x for (c, x, _), _ in pos.items() if c == "escalator"}
    assert escalators == {350.0, 850.0}, f"扶梯应在东西两侧 350/850，实为 {escalators}"
