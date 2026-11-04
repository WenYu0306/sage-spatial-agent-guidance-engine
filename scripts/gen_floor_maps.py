"""从 seed 数据生成三层真实商场底图（单一数据源，杜绝图文漂移）。

输出：
- deploy/maps/{b1,f1,f2}.svg                — 底图资产（M2 服务化时经 /static/maps/ 挂载）
- packages/map-render/src/assets/floors.ts  — 前端内嵌资产（FloorPlan 以 <g> 叠加渲染）

布局约定（与 deploy/seed/tests/test_map_grid.py 同一规则）：
- 1200x800 viewBox；外墙 24..1176 x 24..776
- 走廊五段：y=260/560 横排（x 150..1050）、x=150/600/1050 纵排（y 260..560），宽 34
- 中庭：圆心 (600,410) r=85；中庭服务岛（info_desk）位于其内
- 店面矩形居中于点位；锚店（超市/影院）加大；垂直交通图形位于设施点位

碰撞自检：店面/设施图形与走廊、彼此之间不得重叠（违者生成即失败，不允许带病出图）。
"""

from __future__ import annotations

import json
from pathlib import Path
from xml.sax.saxutils import escape

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "deploy/seed/data"
MAPS = ROOT / "deploy/maps"
ASSET_TS = ROOT / "packages/map-render/src/assets/floors.ts"

CAT_STYLE: dict[str, tuple[str, str]] = {
    **{c: ("#fff7ed", "#fdba74") for c in
       ("chinese", "hotpot", "japanese", "western", "coffee_tea", "bakery", "fastfood")},
    **{c: ("#eff6ff", "#93c5fd") for c in
       ("fashion", "shoes_bags", "digital", "beauty", "jewelry",
        "toys_books", "glasses", "supermarket")},
    **{c: ("#f0fdf4", "#86efac") for c in ("cinema", "gym", "kids_play", "education")},
    **{c: ("#fafaf9", "#d6d3d1") for c in ("salon", "life_service")},
}
ANCHOR_SIZE = {"supermarket": (200, 120), "cinema": (190, 150)}
ANCHOR_MIN_HOT = 80  # 锚店按热度判定（便利店等小型超市不放大）
ROOM_W, ROOM_H = 84, 72

CH = 17  # 走廊半宽
CORRIDOR_BANDS = [  # (x, y, w, h)
    (150 - CH, 260 - CH, 900 + 2 * CH, 2 * CH),   # 北横
    (150 - CH, 560 - CH, 900 + 2 * CH, 2 * CH),   # 南横
    (150 - CH, 260 - CH, 2 * CH, 300 + 2 * CH),   # 西纵
    (600 - CH, 260 - CH, 2 * CH, 300 + 2 * CH),   # 中纵
    (1050 - CH, 260 - CH, 2 * CH, 300 + 2 * CH),  # 东纵
]
ATRIUM = (600.0, 410.0, 85.0)
FAC_COLOR = {"toilet": "#0e7490", "nursing_room": "#be185d", "info_desk": "#16a34a",
             "parking": "#475569", "charging_station": "#b45309", "atm": "#7c3aed"}


def _esc(s: str) -> str:
    return escape(str(s))


def _load() -> tuple[dict, dict[str, list[dict]], list[dict]]:
    tv = yaml.safe_load((DATA / "tenant_venue.yaml").read_text(encoding="utf-8"))
    shops: dict[str, list[dict]] = {}
    for f, floor in (("pois_b1.yaml", "B1"), ("pois_f1.yaml", "F1"), ("pois_f2.yaml", "F2")):
        d = yaml.safe_load((DATA / f).read_text(encoding="utf-8"))
        shops[floor] = [{**p, "floor": floor} for p in d["pois"]]
    fac = yaml.safe_load((DATA / "facilities.yaml").read_text(encoding="utf-8"))
    return tv, shops, fac["pois"]


def _rect(x, y, w, h, fill, stroke="", rx=0, sw=0, cls="") -> str:
    a = f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="{rx:g}" fill="{fill}"'
    if stroke:
        a += f' stroke="{stroke}" stroke-width="{sw:g}"'
    if cls:
        a += f' class="{cls}"'
    return a + "/>"


def _text(x, y, s, size, fill, weight="normal", anchor="middle", cls="") -> str:
    a = (f'<text x="{x:g}" y="{y:g}" font-size="{size:g}" fill="{fill}" '
         f'font-weight="{weight}" text-anchor="{anchor}"')
    if cls:
        a += f' class="{cls}"'
    return a + f">{_esc(s)}</text>"


def _corridors() -> list[str]:
    out = [_rect(x, y, w, h, "#e2e8f0", "#cbd5e1", 0, 0.75, "corridor")
           for x, y, w, h in CORRIDOR_BANDS]
    return out


def _atrium() -> list[str]:
    cx, cy, r = ATRIUM
    out = [f'<circle cx="{cx:g}" cy="{cy:g}" r="{r:g}" fill="#eef2ff" stroke="#c7d2fe" '
           f'stroke-width="1.5" stroke-dasharray="5 4" class="atrium"/>',
           f'<circle cx="{cx:g}" cy="{cy:g}" r="52" fill="none"'
           f' stroke="#e0e7ff" stroke-width="1"/>']
    for px, py in ((560, 362), (640, 362), (560, 462), (640, 462)):
        out.append(f'<circle cx="{px}" cy="{py}" r="5.5" fill="#d9f99d"'
                   f' stroke="#a3e635" stroke-width="1"/>')
    out.append(_text(cx, cy - 6, "中庭", 17, "#818cf8", "600"))
    return out


def _shell(floor: str, venue: str) -> list[str]:
    out = [_rect(24, 24, 1152, 752, "#ffffff", "#64748b", 12, 4)]
    # 南主入口（x 552..648 剖开外墙）
    out += [_rect(552, 20, 96, 10, "#f8fafc"),
            _text(600, 48, "主入口", 12, "#64748b"),
            '<path d="M 592 54 L 600 64 L 608 54 Z" fill="#94a3b8"/>']
    # 东西次入口
    out += [_rect(20, 377, 10, 66, "#f8fafc"), _text(60, 414, "次入口", 11, "#94a3b8"),
            _rect(1170, 377, 10, 66, "#f8fafc"), _text(1140, 414, "次入口", 11, "#94a3b8")]
    out.append(_text(44, 70, f"{floor} 层平面图", 24, "#0f172a", "700", "start"))
    out.append(_text(44, 94, f"{venue} · 演示数据", 12.5, "#64748b", anchor="start"))
    return out


def _chrome(scale: float) -> list[str]:
    out = ['<circle cx="1128" cy="750" r="16" fill="#ffffff" stroke="#94a3b8" stroke-width="1.5"/>',
           '<path d="M 1128 738 L 1123 754 L 1133 754 Z" fill="#475569"/>',
           _text(1128, 764, "N", 9, "#475569")]
    m20 = round(20 / scale, 1)
    out += [f'<line x1="40" y1="744" x2="{40 + m20:g}" y2="744"'
            f' stroke="#475569" stroke-width="1.5"/>']
    for tx in (40, 40 + m20 / 2, 40 + m20):
        out.append(f'<line x1="{tx:g}" y1="740" x2="{tx:g}" y2="748"'
                   f' stroke="#475569" stroke-width="1"/>')
    out += [_text(40, 736, "0", 9.5, "#475569"), _text(40 + m20 / 2, 736, "10", 9.5, "#475569"),
            _text(40 + m20, 736, "20 m", 9.5, "#475569"),
            _text(1160, 792, "演示底图 · 生成于 scripts/gen_floor_maps.py",
                  9, "#94a3b8", anchor="end")]
    return out


def _shops(shops: list[dict]) -> list[str]:
    out: list[str] = []
    for p in shops:
        x, y, cat, name = float(p["x"]), float(p["y"]), p["category"], p["name"]
        is_anchor = cat in ANCHOR_SIZE and float(p.get("hot", 0)) >= ANCHOR_MIN_HOT
        w, h = ANCHOR_SIZE.get(cat, (ROOM_W, ROOM_H)) if is_anchor else (ROOM_W, ROOM_H)
        fill, stroke = CAT_STYLE[cat]
        out.append(_rect(x - w / 2, y - h / 2, w, h, fill, stroke, 7, 1.5, "shop"))
        size = 15 if is_anchor else (11 if len(name) >= 7 else 12.5)
        weight = "700" if is_anchor else "normal"
        out.append(_text(x, y + 4, name, size, "#1e293b", weight, cls="shop-label"))
    return out


def _badge(x, y, char, color, label) -> list[str]:
    return [f'<g class="facility">',
            f'<circle cx="{x:g}" cy="{y:g}" r="12" fill="#ffffff" stroke="{color}" stroke-width="1.5"/>',
            _text(x, y + 4.5, char, 12, color, "700"),
            _text(x, y + 28, label, 10.5, "#475569"),
            "</g>"]


def _facilities(facs: list[dict], floor: str) -> list[str]:
    out: list[str] = []
    for f in facs:
        if f["floor"] != floor:
            continue
        x, y, cat = float(f["x"]), float(f["y"]), f["category"]
        name = f["name"]
        if cat == "elevator":
            out += ['<g class="facility">',
                    _rect(x - 28, y - 19, 56, 38, "#fef9c3", "#ca8a04", 6, 1.5),
                    f'<line x1="{x - 28:g}" y1="{y - 19:g}" x2="{x + 28:g}" y2="{y + 19:g}" stroke="#ca8a04" stroke-width="1"/>',
                    f'<line x1="{x + 28:g}" y1="{y - 19:g}" x2="{x - 28:g}" y2="{y + 19:g}" stroke="#ca8a04" stroke-width="1"/>',
                    _text(x, y + 36, "直梯", 11, "#92400e"), "</g>"]
        elif cat == "escalator":
            up = floor != "F2"  # F1 上行 / F2 下行
            out += ['<g class="facility">',
                    _rect(x - 32, y - 14, 64, 28, "#ffedd5", "#f97316", 4, 1.5)]
            for i in (-16, 0, 16):
                dy = 4 if up else -4
                out.append(f'<path d="M {x + i - 6:g} {y + dy:g} L {x + i:g} {y - dy:g} '
                           f'L {x + i + 6:g} {y + dy:g}" fill="none" stroke="#c2410c" stroke-width="2"/>')
            out += [_text(x, y + 28, name.split()[-1], 11, "#9a3412"), "</g>"]
        elif cat == "info_desk":
            out += ['<g class="facility">', _rect(x - 20, y - 18, 40, 36, "#dcfce7", "#16a34a", 8, 1.5),
                    _text(x, y + 5, "服", 13, "#166534", "700"),
                    _text(x, y + 34, "服务台", 10.5, "#475569"), "</g>"]
        elif cat == "toilet":
            out += _badge(x, y, "卫", FAC_COLOR[cat], "卫生间")
        elif cat == "nursing_room":
            out += _badge(x, y, "婴", FAC_COLOR[cat], "母婴室")
        elif cat == "parking":
            short = name.split(" ", 1)[1] if " " in name else name
            out += _badge(x, y, "停", FAC_COLOR[cat], short)
        elif cat == "charging_station":
            out += _badge(x, y, "充", FAC_COLOR[cat], "充电桩")
        elif cat == "atm":
            out += _badge(x, y, "银", FAC_COLOR[cat], "ATM")
    return out


def _check(shops: list[dict], facs_floor: list[dict]) -> None:
    """碰撞自检：实体矩形两两不重叠；实体不压走廊；店面不进中庭。"""
    boxes: list[tuple[str, tuple]] = []
    for p in shops:
        cat = p["category"]
        is_anchor = cat in ANCHOR_SIZE and float(p.get("hot", 0)) >= ANCHOR_MIN_HOT
        w, h = ANCHOR_SIZE.get(cat, (ROOM_W, ROOM_H)) if is_anchor else (ROOM_W, ROOM_H)
        x, y = float(p["x"]), float(p["y"])
        boxes.append((p["name"], (x - w / 2, y - h / 2, w, h)))
    for f in facs_floor:
        x, y, cat = float(f["x"]), float(f["y"]), f["category"]
        if cat == "elevator":
            boxes.append((f["name"], (x - 28, y - 19, 56, 38)))
        elif cat == "escalator":
            boxes.append((f["name"], (x - 32, y - 14, 64, 28)))
        elif cat == "info_desk":
            boxes.append((f["name"], (x - 20, y - 18, 40, 36)))
        else:
            boxes.append((f["name"], (x - 12, y - 12, 24, 24)))

    def ov(a, b) -> bool:
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah

    bad = []
    for i, (na, a) in enumerate(boxes):
        for nb, b in boxes[i + 1:]:
            if ov(a, b):
                bad.append(f"{na} ↔ {nb}")
        for cx, cy, cw, chh in CORRIDOR_BANDS:
            if ov(a, (cx, cy, cw, chh)):
                bad.append(f"{na} 压走廊")
    cx, cy, r = ATRIUM
    for name, (x, y, w, h) in boxes:
        if "服务台" in name:
            continue
        nx = max(x, min(cx, x + w))
        ny = max(y, min(cy, y + h))
        if (nx - cx) ** 2 + (ny - cy) ** 2 < r * r:
            bad.append(f"{name} 侵入中庭净空")
    if bad:
        raise SystemExit("碰撞自检失败：\n  " + "\n  ".join(sorted(set(bad))))


FONT = "font-family=\"'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif\""


def build() -> dict[str, str]:
    tv, shops, facs = _load()
    venue = tv["venue"]["name"]
    scale = float(tv["map_layers"]["F1"]["scale_meter"])
    out: dict[str, str] = {}
    for floor in ("B1", "F1", "F2"):
        facs_floor = [f for f in facs if f["floor"] == floor]
        _check(shops[floor], facs_floor)
        inner = "\n".join(
            _shell(floor, venue) + _corridors() + _atrium()
            + _shops(shops[floor]) + _facilities(facs, floor) + _chrome(scale))
        out[floor] = f'<g {FONT} class="floor-base">\n{inner}\n</g>'
        svg = (f'<?xml version="1.0" encoding="UTF-8"?>\n'
               f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 800" {FONT}>\n'
               f'{out[floor]}\n</svg>\n')
        MAPS.mkdir(exist_ok=True)
        (MAPS / f"{floor.lower()}.svg").write_text(svg, encoding="utf-8")
    ts = (
        "/** 由 scripts/gen_floor_maps.py 从 deploy/seed/data 生成——勿手改，重跑生成器更新。 */\n"
        "export const FLOOR_SVGS: Record<string, string> = "
        + json.dumps(out, ensure_ascii=False, indent=2).replace(
            '{\n  "B1"', '{\n  "B1"') + ";\n"
    )
    ASSET_TS.parent.mkdir(parents=True, exist_ok=True)
    ASSET_TS.write_text(ts, encoding="utf-8")
    return out


if __name__ == "__main__":
    built = build()
    for k, v in built.items():
        print(f"{k}: {len(v)} 字符 inner markup")
    print(f"输出：deploy/maps/{{b1,f1,f2}}.svg + {ASSET_TS.relative_to(ROOT)}")
