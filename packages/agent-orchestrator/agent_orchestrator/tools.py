"""八工具注册表（PRD 8.2 逐项）：超时、降级、入参指纹去重。

- 数据类工具（poi/facility/promotion/coupon）直读共享 PRD-DDL 表（demo 阶段
  DB 即契约的数据形态；M8 服务化后换 endpoint URL，接口不变）
- 算法类 route.plan / knowledge.query 走兄弟模块 HTTP 服务（import-linter 纪律）
- recommend.rank 临时实现=距离排序（其声明的降级路径），完整 8 因子随 M7 替换
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass

import httpx
import psycopg

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


class ToolError(Exception):
    """工具业务失败；error_code 对应 M0 错误码表。"""


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    data: object
    error_code: int | None = None
    degraded: bool = False


@dataclass
class ToolContext:
    tenant_id: int
    venue_id: int
    tenant_code: str
    venue_name: str
    dsn: str
    http_route: httpx.Client
    http_knowledge: httpx.Client
    http_recommender: httpx.Client | None = None  # M7 打分服务（None=直接降级）
    position: dict | None = None  # {"x": float, "y": float, "floor_id": int|None}
    prefer_accessible: bool = False


@dataclass(frozen=True)
class ToolSpec:
    code: str
    description: str
    timeout_ms: int
    handler: object
    fallback_note: str  # PRD 8.2 的失败降级语义


def fingerprint(code: str, args: dict) -> str:
    """入参指纹：同一工具同一入参一轮内不得重复调用。"""
    raw = code + "|" + json.dumps(args, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _conn(ctx: ToolContext):
    return psycopg.connect(ctx.dsn)


def _resolve_category_codes(cur, ctx: ToolContext, name_or_code: str) -> list[str]:
    """业态名或 code → [该 code 及其子类 code]（如 火锅 → [hotpot]）。"""
    cur.execute(
        "select code from poi_categories where tenant_id=%s and (name=%s or code=%s)",
        (ctx.tenant_id, name_or_code, name_or_code),
    )
    rows = [r[0] for r in cur.fetchall()]
    if not rows:
        return [name_or_code]
    cur.execute(
        "select code from poi_categories where tenant_id=%s and parent_code = any(%s)",
        (ctx.tenant_id, rows),
    )
    return sorted(set(rows) | {r[0] for r in cur.fetchall()})


def _is_open_now(business_hours: dict) -> bool:
    today = WEEKDAYS[dt.datetime.now().weekday()]
    ranges = business_hours.get(today) or []
    now = dt.datetime.now().strftime("%H:%M")
    for r in ranges:
        try:
            start, end = str(r).split("-")
        except ValueError:
            continue
        if start <= now <= end:
            return True
    return False


def _floor_name_map(cur, ctx: ToolContext) -> dict[int, str]:
    cur.execute("select id, name from floors where venue_id=%s", (ctx.venue_id,))
    return dict(cur.fetchall())


# ---------- 各工具 handler（签名统一 (args, ctx, cur 已在调用方持有)） ----------


def _poi_search(args: dict, ctx: ToolContext) -> ToolResult:
    with _conn(ctx) as conn, conn.cursor() as cur:
        codes = (
            _resolve_category_codes(cur, ctx, args["category"]) if args.get("category") else None
        )
        sql = (
            "select p.id, p.name, p.category_code, f.name, p.tags, p.hot_score, "
            "p.business_hours from pois p join floors f on f.id = p.floor_id "
            "where p.tenant_id=%s and p.venue_id=%s and p.deleted_at is null "
            "and p.status='published'"
        )
        params: list = [ctx.tenant_id, ctx.venue_id]
        if codes:
            sql += " and p.category_code = any(%s)"
            params.append(codes)
        if args.get("keyword"):
            sql += " and p.name ilike %s"
            params.append(f"%{args['keyword']}%")
        if args.get("floor_name"):
            sql += " and f.name = %s"
            params.append(args["floor_name"])
        if args.get("scene_tag"):
            # 场景词与标签双向子串包含（"家庭聚餐"命中 tag[聚餐]，"情侣约会"命中 tag[约会]）：
            # 精确 jsonb @> 会把自然语言场景词全部搜空（用户实测回归根因）
            sql += (
                " and exists (select 1 from jsonb_array_elements_text(p.tags) t "
                "where t like '%%' || %s || '%%' or %s like '%%' || t || '%%')"
            )
            params.extend([args["scene_tag"], args["scene_tag"]])
        sql += " order by p.hot_score desc limit 12"
        cur.execute(sql, params)
        rows = cur.fetchall()
    items = []
    for pid, name, cat, floor, tags, hot, hours in rows:
        if args.get("open_only") and not _is_open_now(hours):
            continue
        items.append({"poi_id": pid, "name": name, "category": cat,
                      "floor": floor, "tags": tags, "hot_score": float(hot)})
    return ToolResult(True, {"items": items})


def _poi_detail(args: dict, ctx: ToolContext) -> ToolResult:
    with _conn(ctx) as conn, conn.cursor() as cur:
        cur.execute(
            "select p.id, p.name, p.category_code, f.name, p.intro, p.business_hours, p.tags "
            "from pois p join floors f on f.id=p.floor_id "
            "where p.tenant_id=%s and p.venue_id=%s and (p.id=%s or p.name=%s) "
            "and p.deleted_at is null",
            (ctx.tenant_id, ctx.venue_id, args.get("poi_id") or 0, args.get("poi_name") or ""),
        )
        row = cur.fetchone()
    if not row:
        return ToolResult(True, {"item": None, "hint": "换个说法再试试"}, degraded=True)
    pid, name, cat, floor, intro, hours, tags = row
    return ToolResult(True, {"item": {"poi_id": pid, "name": name, "category": cat,
                                      "floor": floor, "intro": intro,
                                      "business_hours": hours, "tags": tags}})


def _facility_nearest(args: dict, ctx: ToolContext) -> ToolResult:
    with _conn(ctx) as conn, conn.cursor() as cur:
        codes = _resolve_category_codes(cur, ctx, args["facility"])
        cur.execute(
            "select p.id, p.name, f.name, p.position_x, p.position_y, p.floor_id, "
            "p.hot_score from pois p join floors f on f.id=p.floor_id "
            "join poi_categories c on c.code=p.category_code and c.tenant_id=p.tenant_id "
            "where p.tenant_id=%s and p.venue_id=%s and p.category_code = any(%s) "
            "and p.deleted_at is null",
            (ctx.tenant_id, ctx.venue_id, codes),
        )
        rows = cur.fetchall()
        floor_names = _floor_name_map(cur, ctx)
    pos = ctx.position or {}
    here = pos.get("floor_id")
    px, py = pos.get("x"), pos.get("y")
    has_position = px is not None and here is not None

    def dist(row):
        if has_position and row[5] == here:
            return ((float(row[3]) - px) ** 2 + (float(row[4]) - py) ** 2) ** 0.5
        return 1e9  # 跨层排后

    rows.sort(key=lambda r: (dist(r), -float(r[6] or 0)))
    if not has_position:
        # 无位置上下文时"最近"无从谈起：按热度返回，不声称同层（回归：曾恒 same_floor=True）
        rows.sort(key=lambda r: -float(r[6] or 0))
    items = [
        {"poi_id": r[0], "name": r[1], "floor": r[2],
         "same_floor": has_position and r[5] == here}
        for r in rows[:3]
    ]
    if not items:
        return ToolResult(True, {"items": [], "hint": "floor_map"}, degraded=True)
    return ToolResult(True, {"items": items, "floor_names": floor_names})


def _route_plan(args: dict, ctx: ToolContext) -> ToolResult:
    to_name = args.get("to_poi_name")
    from_name = args.get("from_poi_name")
    to_poi_id = args.get("to_poi_id")
    with _conn(ctx) as conn, conn.cursor() as cur:
        goal = None
        if to_poi_id:
            # 上游工具（facility.nearest）已选定的目标直取——按名 ilike 解析会在
            # 并列 hot_score 的同名设施间随机选层（回归：F1 问厕被指去 B1）
            cur.execute(
                "select n.id from pois p join route_nodes n on n.poi_id=p.id "
                "where p.id=%s and p.tenant_id=%s and p.venue_id=%s",
                (to_poi_id, ctx.tenant_id, ctx.venue_id),
            )
            goal = cur.fetchone()
        if goal is None and to_name:
            cur.execute(
                "select n.id from pois p join route_nodes n on n.poi_id=p.id "
                "where p.tenant_id=%s and p.venue_id=%s and p.name=%s",
                (ctx.tenant_id, ctx.venue_id, to_name),
            )
            goal = cur.fetchone()
        if not goal and to_name:  # 泛称解析（"电影院"→"巨幕星云影院"）
            cur.execute(
                "select n.id from pois p join route_nodes n on n.poi_id=p.id "
                "join poi_categories c on c.code=p.category_code and c.tenant_id=p.tenant_id "
                "where p.tenant_id=%s and p.venue_id=%s "
                "and (p.name ilike %s or c.name ilike %s or p.category_code ilike %s) "
                "order by p.hot_score desc limit 1",
                (ctx.tenant_id, ctx.venue_id, f"%{to_name}%", f"%{to_name}%", f"%{to_name}%"),
            )
            goal = cur.fetchone()
        start = None
        if from_name:
            cur.execute(
                "select n.id from pois p join route_nodes n on n.poi_id=p.id "
                "where p.tenant_id=%s and p.venue_id=%s and p.name=%s",
                (ctx.tenant_id, ctx.venue_id, from_name),
            )
            start = cur.fetchone()
    if not goal:
        return ToolResult(True, {"hint": "文字指引", "message": f"没找到「{to_name}」的位置"},
                          degraded=True)
    if not start:
        if not (ctx.position and ctx.position.get("floor_id")):
            return ToolResult(True, {"hint": "floor_map", "message": "缺少起点"}, degraded=True)
        # 起点为设备/用户位置：取该层最近走廊节点
        with _conn(ctx) as conn, conn.cursor() as cur:
            cur.execute(
                "select id from route_nodes where floor_id=%s and node_type='waypoint' "
                "order by (x-%s)^2+(y-%s)^2 limit 1",
                (ctx.position["floor_id"], ctx.position.get("x", 600), ctx.position.get("y", 400)),
            )
            row = cur.fetchone()
        if not row:
            return ToolResult(True, {"hint": "floor_map", "message": "缺少起点"}, degraded=True)
        start = row
    try:
        resp = ctx.http_route.post(
            "/route/plan",
            json={"tenant_code": ctx.tenant_code, "venue_name": ctx.venue_name,
                  "start_node_id": start[0], "goal_node_id": goal[0],
                  "accessible_only": ctx.prefer_accessible or bool(args.get("prefer_accessible"))},
        )
        body = resp.json()
    except httpx.HTTPError as exc:
        return ToolResult(True, {"hint": "文字指引", "message": f"路线服务暂不可用：{exc}"},
                          error_code=2004, degraded=True)
    if "error_code" in body:
        if body["error_code"] == 2003:
            return ToolResult(True, {"hint": "文字指引", "message": "目的地暂不可达"},
                              error_code=2003, degraded=True)
        return ToolResult(True, {"hint": "floor_map", "message": "路网未构建"},
                          error_code=2004, degraded=True)
    return ToolResult(True, body)


def _promotion_list(args: dict, ctx: ToolContext) -> ToolResult:
    with _conn(ctx) as conn, conn.cursor() as cur:
        cond_poi = "and a.poi_id = %s" if args.get("poi_name") else ""
        params_a: list = [ctx.tenant_id, ctx.venue_id]
        if args.get("poi_name"):
            cur.execute(
                "select id from pois where tenant_id=%s and venue_id=%s and name=%s",
                (ctx.tenant_id, ctx.venue_id, args["poi_name"]),
            )
            row = cur.fetchone()
            if not row:
                return ToolResult(True, {"activities": [], "coupons": []})
            params_a.append(row[0])
        cur.execute(
            "select a.id, a.title, a.description, a.act_type, a.poi_id "
            "from activities a where a.tenant_id=%s and a.venue_id=%s "
            f"and a.status='active' and now() between a.start_at and a.end_at "
            f"and a.deleted_at is null {cond_poi}",
            params_a,
        )
        acts = [{"activity_id": r[0], "title": r[1], "description": r[2],
                 "type": r[3], "poi_id": r[4]} for r in cur.fetchall()]
        cond_c = "and c.poi_id = %s" if args.get("poi_name") else ""
        params_c: list = [ctx.tenant_id, ctx.venue_id]
        if args.get("poi_name"):
            params_c.append(params_a[2])
        cur.execute(
            "select c.id, c.title, c.coupon_type, c.threshold, c.value, c.total_qty, "
            "c.claimed_qty, p.name from coupons c "
            "left join pois p on p.id = c.poi_id "
            "where c.tenant_id=%s and c.venue_id=%s "
            f"and c.status='active' and now() between c.start_at and c.end_at "
            f"and c.deleted_at is null {cond_c}",
            params_c,
        )
        cps = [{"coupon_id": r[0], "title": r[1], "type": r[2], "threshold": float(r[3]),
                "value": float(r[4]), "remaining": r[5] - r[6],
                # 关联门店名：回答与幻觉校验白名单的数据依据（回归 E05）
                "poi_name": r[7]} for r in cur.fetchall()]
    return ToolResult(True, {"activities": acts, "coupons": cps})


def _coupon_claim(args: dict, ctx: ToolContext) -> ToolResult:
    title = args.get("coupon_title") or ""
    anonymous = args.get("anonymous_id") or "anonymous-demo"
    with _conn(ctx) as conn, conn.cursor() as cur:
        cur.execute(
            "select id, total_qty, claimed_qty from coupons "
            "where tenant_id=%s and venue_id=%s and title ilike %s and deleted_at is null",
            (ctx.tenant_id, ctx.venue_id, f"%{title}%"),
        )
        row = cur.fetchone()
        if not row:
            return ToolResult(True, {"claimed": False, "message": "没有找到这张券"}, degraded=True)
        coupon_id, total_qty, claimed_qty = row
        if claimed_qty >= total_qty:
            return ToolResult(True, {"claimed": False, "message": "券已领完"})
        key = f"{coupon_id}:{anonymous}"
        cur.execute(
            "insert into coupon_claims (tenant_id, coupon_id, anonymous_id, idempotency_key) "
            "values (%s, %s, %s, %s) on conflict (idempotency_key) do nothing returning id",
            (ctx.tenant_id, coupon_id, anonymous, key),
        )
        inserted = cur.fetchone()
        if not inserted:
            return ToolResult(True, {"claimed": True, "duplicate": True,
                                     "message": "你已领过这张券，不重复发放"})
        cur.execute(
            "update coupons set claimed_qty = claimed_qty + 1 "
            "where id=%s and claimed_qty < total_qty returning id",
            (coupon_id,),
        )
        if not cur.fetchone():
            conn.rollback()
            return ToolResult(True, {"claimed": False, "message": "券已领完"})
    return ToolResult(True, {"claimed": True, "duplicate": False, "coupon_id": coupon_id})


def _knowledge_query(args: dict, ctx: ToolContext) -> ToolResult:
    try:
        payload = {"tenant_id": ctx.tenant_id, "venue_id": ctx.venue_id,
                   "query": args.get("query") or ""}
        if args.get("threshold") is not None:
            payload["threshold"] = args["threshold"]
        resp = ctx.http_knowledge.post("/knowledge/retrieve", json=payload)
        body = resp.json()
    except httpx.HTTPError as exc:
        return ToolResult(True, {"items": [], "message": f"知识服务暂不可用：{exc}"},
                          error_code=3004, degraded=True)
    items = body.get("items", [])
    keyword_used = any(i["source"] == "keyword" for i in items)
    return ToolResult(True, {"items": items, "degraded": keyword_used})


def _recommend_rank(args: dict, ctx: ToolContext) -> ToolResult:
    """M7 八因子打分（HTTP）；服务不可用降级距离升序（PRD 8.2 声明的降级路径）。"""
    ids = args.get("candidates") or []
    if not ids:
        return ToolResult(True, {"ranked": []})
    if ctx.http_recommender is not None:
        try:
            resp = ctx.http_recommender.post("/recommend/rank", json={
                "tenant_id": ctx.tenant_id, "venue_id": ctx.venue_id,
                "candidates": [int(i) for i in ids],
                "position": ctx.position or {}, "tags": args.get("tags") or [],
                "promotion_poi_ids": args.get("promotion_poi_ids") or [],
            })
            if resp.status_code == 200 and "ranked" in resp.json():
                return ToolResult(True, resp.json())
        except httpx.HTTPError:
            pass  # 落入下方距离降级
    return _rank_by_distance(args, ctx)


def _rank_by_distance(args: dict, ctx: ToolContext) -> ToolResult:
    ids = args.get("candidates") or []
    with _conn(ctx) as conn, conn.cursor() as cur:
        cur.execute(
            "select p.id, p.name, f.name, p.position_x, p.position_y "
            "from pois p join floors f on f.id=p.floor_id "
            "where p.tenant_id=%s and p.venue_id=%s and p.id = any(%s) "
            "and p.deleted_at is null",
            (ctx.tenant_id, ctx.venue_id, ids),
        )
        rows = cur.fetchall()
    pos = ctx.position or {}
    px, py = pos.get("x", 600.0), pos.get("y", 400.0)

    def dist(r):
        return abs(float(r[3]) - px) + abs(float(r[4]) - py)  # 同层近似；跨层由 M7 处理

    rows.sort(key=dist)
    ranked = [{"poi_id": r[0], "name": r[1], "floor": r[2],
               "reasons": ["距你最近（临时排序，M7 接入 8 因子打分）"]} for r in rows]
    return ToolResult(True, {"ranked": ranked, "temporary": True})


TOOLS: dict[str, ToolSpec] = {
    s.code: s
    for s in (
        ToolSpec("poi.search", "按分类/标签/楼层/营业状态/关键词检索 POI", 1500,
                 _poi_search, "返回空 + 提示换个说法"),
        ToolSpec("poi.detail", "查 POI 详情与营业时间", 1000, _poi_detail, "跳过详情"),
        ToolSpec("facility.nearest", "查最近的设施", 1500, _facility_nearest,
                 "返回楼层平面图入口"),
        ToolSpec("route.plan", "规划跨楼层路线", 2000, _route_plan, "返回文字方向指引"),
        ToolSpec("promotion.list", "查当前活动与优惠", 1500, _promotion_list,
                 "不带优惠继续回答"),
        ToolSpec("coupon.claim", "领取优惠券（幂等键=券+顾客）", 2000, _coupon_claim,
                 "提示稍后重试，不重复扣库存"),
        ToolSpec("knowledge.query", "检索场地知识（RAG）", 2500, _knowledge_query,
                 "降级为关键词检索，标记 degraded"),
        ToolSpec("recommend.rank", "对候选 POI 排序", 1000, _recommend_rank,
                 "按距离升序兜底"),
    )
}


def run_tool(code: str, args: dict, ctx: ToolContext, seen: set[str] | None = None) -> ToolResult:
    """统一入口：注册表校验 → 指纹去重 → 执行。异常转 error_code，不抛给用户。"""
    spec = TOOLS.get(code)
    if spec is None:
        return ToolResult(False, {}, error_code=9999)
    fp = fingerprint(code, args)
    if seen is not None:
        if fp in seen:
            return ToolResult(False, {"message": "同一工具同一入参本轮已调用"},
                              error_code=3005, degraded=True)
        seen.add(fp)
    try:
        return spec.handler(args, ctx)
    except ToolError as exc:
        return ToolResult(False, {"message": str(exc)}, error_code=2002, degraded=True)
    except psycopg.Error as exc:
        return ToolResult(False, {"message": f"数据访问失败：{exc}"},
                          error_code=9999, degraded=True)
