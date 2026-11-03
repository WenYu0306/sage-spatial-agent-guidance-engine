"""M7 特征装配：从共享 PRD-DDL 表读泛化列（D-016 数据通道；零业务词）。

读取范围：pois 的坐标/楼层/营业时间/标签/热度/权重、floors.level、
map_layers.scale_meter、route_nodes 主动线节点（waypoint）。
营销旗标（has_promotion）不在本模块——由调用方传入（业务表不进内核）。
"""

from __future__ import annotations

import datetime as dt
import math

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
CLOSING_SOON_WINDOW = 30  # 分钟：距打烊不足 30 分钟记 closing_soon

SQL_CANDIDATES = """
select p.id, p.name, p.position_x, p.position_y, p.floor_id, p.business_hours,
       p.tags, p.hot_score, p.recommend_weight, f.level, m.scale_meter, f.name
from pois p
join floors f on f.id = p.floor_id
left join map_layers m on m.floor_id = p.floor_id and m.status = 'published'
where p.tenant_id = %s and p.venue_id = %s
  and p.deleted_at is null and p.status = 'published'
  and p.id = any(%s)
"""

SQL_TRUNK = """
select floor_id, x, y from route_nodes
where tenant_id = %s and venue_id = %s and node_type = 'waypoint'
"""


def _parse_hours(bh: dict) -> list[tuple[dt.time, dt.time]]:
    """business_hours JSONB → 当天适用时段列表（今天无配置则用任一天的并集兜底）。"""
    ranges = []
    for day in WEEKDAYS:
        for span in bh.get(day) or []:
            try:
                start, end = span.split("-")
                ranges.append((dt.time.fromisoformat(start),
                               dt.time.fromisoformat(end)))
            except ValueError:
                continue
    return ranges


def business_status(bh: dict, now: dt.datetime) -> str:
    """营业中 / 即将打烊 / 休息（PRD 8.4 营业状态因子的输入）。"""
    spans = _parse_hours(bh if isinstance(bh, dict) else {})
    today = now.date().strftime("%a").lower()[:3]
    today_spans = []
    for span in (bh or {}).get(today) or []:
        try:
            start, end = span.split("-")
            today_spans.append((dt.time.fromisoformat(start),
                                dt.time.fromisoformat(end)))
        except ValueError:
            continue
    check = now.time().replace(tzinfo=None)
    for start, end in today_spans or spans:
        if start <= check <= end:
            mins_to_close = (dt.datetime.combine(now.date(), end)
                             - dt.datetime.combine(now.date(), check)).total_seconds() / 60
            return "closing_soon" if mins_to_close <= CLOSING_SOON_WINDOW else "open"
    return "closed"


def _dist(ax, ay, bx, by) -> float:
    return math.hypot(float(ax) - float(bx), float(ay) - float(by))


def gather(cur, tenant_id: int, venue_id: int, candidate_ids: list[int],
           position: dict, now: dt.datetime | None = None) -> list[dict]:
    """装配打分内核所需的候选特征（SVG 坐标 × scale_meter 折算米）。"""
    now = now or dt.datetime.now()
    cur.execute(SQL_CANDIDATES, (tenant_id, venue_id, list(candidate_ids)))
    cand_rows = cur.fetchall()  # 立即取走：同游标跑 SQL_TRUNK 会丢弃该结果集
    trunk: dict[int, list[tuple[float, float]]] = {}
    cur.execute(SQL_TRUNK, (tenant_id, venue_id))
    for fid, x, y in cur.fetchall():
        trunk.setdefault(fid, []).append((float(x), float(y)))
    pos_floor = position.get("floor_id")
    pos_level = None
    if pos_floor is not None:
        cur.execute("select level from floors where id=%s", (pos_floor,))
        row = cur.fetchone()
        pos_level = row[0] if row else None
    out = []
    for (pid, name, x, y, floor_id, bh, tags, hot, weight, level,
         scale, floor_name) in cand_rows:
        scale = float(scale or 1.0)
        dist_m = _dist(position.get("x", 0), position.get("y", 0), x, y) * scale
        td = trunk.get(floor_id) or []
        trunk_dist = min((_dist(x, y, tx, ty) for tx, ty in td), default=1e9) * scale
        out.append({
            "poi_id": pid, "name": name,
            "distance_m": round(dist_m, 1),
            "floor_diff": abs(int(level) - int(pos_level)) if pos_level is not None else 0,
            "business_status": business_status(bh if isinstance(bh, dict) else {},
                                               now),
            "recommend_weight": float(weight),
            "hot_score": float(hot),
            "tags": list(tags or []),
            "trunk_dist_m": round(min(trunk_dist, 1e7), 1),
            "floor": floor_name,
        })
    return out
