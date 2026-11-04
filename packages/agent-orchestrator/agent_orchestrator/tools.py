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
    http_recommender: httpx.Client | None = None
    # M8 内容服务（M2 服务化：业务数据零直读）
    http_content: httpx.Client | None = None  # M7 打分服务（None=直接降级）
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
    params = {"venue_id": ctx.venue_id, "status": "published", "limit": 12}
    if args.get("category"):
        params["category_code"] = args["category"]
    if args.get("keyword"):
        params["keyword"] = args["keyword"]
    if args.get("scene_tag"):
        params["scene_tag"] = args["scene_tag"]
    if args.get("floor_name"):
        fl = ctx.http_content.get("/api/v1/floors", params={"venue_id": ctx.venue_id})
        for f in fl.json().get("items", []):
            if f["name"] == args["floor_name"]:
                params["floor_id"] = f["id"]
    try:
        resp = ctx.http_content.get("/api/v1/pois", params=params)
        body = resp.json()
    except httpx.HTTPError:
        return ToolResult(True, {"items": [], "message": "内容服务暂不可用"},
                          error_code=2004, degraded=True)
    items = [{"poi_id": i["id"], "name": i["name"], "category": i["category_code"],
              "floor": i.get("floor"), "tags": i.get("tags") or [],
              "hot_score": float(i.get("hot_score") or 0)} for i in body.get("items", [])]
    return ToolResult(True, {"items": items})


def _poi_detail(args: dict, ctx: ToolContext) -> ToolResult:
    poi_id = args.get("poi_id")
    name = args.get("poi_name")
    try:
        if poi_id:
            resp = ctx.http_content.get(f"/api/v1/pois/{poi_id}",
                                        params={"venue_id": ctx.venue_id})
        elif name:
            resp = ctx.http_content.get("/api/v1/pois",
                                        params={"venue_id": ctx.venue_id,
                                                "keyword": name, "limit": 1})
        else:
            return ToolResult(True, {"hint": "文字指引", "message": "未指定店铺"},
                              degraded=True)
        body = resp.json()
    except httpx.HTTPError:
        return ToolResult(True, {"hint": "文字指引", "message": "内容服务暂不可用"},
                          error_code=2004, degraded=True)
    row = body if "name" in body else (body.get("items") or [{}])[0]
    if not row.get("name"):
        return ToolResult(True, {"hint": "文字指引", "message": f"没找到「{name}」"},
                          degraded=True)
    bh = row.get("business_hours") or {}
    today = bh.get("holidays") and "节假日除外"
    return ToolResult(True, {"name": row["name"], "floor_hint": row.get("floor_id"),
                             "hours_today": today, "contact": row.get("contact"),
                             "tags": row.get("tags") or []})


def _facility_nearest(args: dict, ctx: ToolContext) -> ToolResult:
    params = {"venue_id": ctx.venue_id, "category_code": args["facility"], "limit": 3}
    pos = ctx.position or {}
    if pos.get("x") is not None and pos.get("floor_id") is not None:
        params.update({"x": pos["x"], "y": pos.get("y", 400), "floor_id": pos["floor_id"]})
    try:
        resp = ctx.http_content.get("/api/v1/pois/nearest", params=params)
        body = resp.json()
    except httpx.HTTPError:
        return ToolResult(True, {"items": [], "hint": "floor_map"}, degraded=True)
    items = [{"poi_id": i["poi_id"], "name": i["name"], "floor": i["floor"],
              "same_floor": i["same_floor"]} for i in body.get("items", [])]
    if not items:
        return ToolResult(True, {"items": [], "hint": "floor_map"}, degraded=True)
    return ToolResult(True, {"items": items, "floor_names": {}})


def _route_plan(args: dict, ctx: ToolContext) -> ToolResult:
    to_name = args.get("to_poi_name")
    from_name = args.get("from_poi_name")
    to_poi_id = args.get("to_poi_id")

    def node_by_poi(pid: int):
        resp = ctx.http_content.get("/api/v1/route-nodes",
                                    params={"venue_id": ctx.venue_id, "poi_id": pid})
        items = resp.json().get("items", [])
        return items[0]["id"] if items else None

    def poi_id_by_name(name: str):
        resp = ctx.http_content.get("/api/v1/pois",
                                    params={"venue_id": ctx.venue_id,
                                            "keyword": name, "limit": 1})
        items = resp.json().get("items", [])
        return items[0]["id"] if items else None

    goal = None
    try:
        if to_poi_id:
            goal = node_by_poi(int(to_poi_id))
        elif to_name:
            pid = poi_id_by_name(to_name)
            goal = node_by_poi(pid) if pid else None
        start = None
        if from_name:
            fpid = poi_id_by_name(from_name)
            start = node_by_poi(fpid) if fpid else None
    except httpx.HTTPError:
        return ToolResult(True, {"hint": "文字指引", "message": "内容服务暂不可用"},
                          error_code=2004, degraded=True)
    if not goal:
        return ToolResult(True, {"hint": "文字指引",
                                 "message": f"没找到「{to_name or ''}」的位置"}, degraded=True)
    if not start:
        if not (ctx.position and ctx.position.get("floor_id")):
            return ToolResult(True, {"hint": "floor_map", "message": "缺少起点"}, degraded=True)
        try:
            resp = ctx.http_route.post(
                "/route/plan/nearest-node",
                json={"tenant_code": ctx.tenant_code, "venue_name": ctx.venue_name,
                      "floor_id": ctx.position["floor_id"],
                      "x": ctx.position.get("x", 600),
                      "y": ctx.position.get("y", 400)})
            row = resp.json()
        except httpx.HTTPError as exc:
            return ToolResult(True, {"hint": "floor_map",
                                     "message": f"起点解析失败：{exc}"}, degraded=True)
        start = row.get("node_id")
        if not start:
            return ToolResult(True, {"hint": "floor_map", "message": "该层无可用路网点"},
                              degraded=True)
    try:
        resp = ctx.http_route.post(
            "/route/plan",
            json={"tenant_code": ctx.tenant_code, "venue_name": ctx.venue_name,
                  "start_node_id": start, "goal_node_id": goal,
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
    try:
        acts = ctx.http_content.get(
            "/api/v1/activities", params={"venue_id": ctx.venue_id, "page_size": 10}).json()
        cps = ctx.http_content.get(
            "/api/v1/coupons", params={"venue_id": ctx.venue_id, "page_size": 10}).json()
    except httpx.HTTPError:
        return ToolResult(True, {"activities": [], "coupons": [], "message": "优惠服务暂不可用"},
                          error_code=2004, degraded=True)
    return ToolResult(True, {
        "activities": [{"activity_id": a["id"], "title": a["title"],
                        "type": a.get("act_type"), "poi_id": a.get("poi_id"),
                        "poi_name": a.get("poi_name")} for a in acts.get("items", [])],
        "coupons": [{"coupon_id": c["id"], "title": c["title"], "type": c["coupon_type"],
                     "threshold": c.get("threshold"), "value": c.get("value"),
                     "remaining": c.get("remaining"), "poi_name": c.get("poi_name")}
                    for c in cps.get("items", [])],
    })


def _coupon_claim(args: dict, ctx: ToolContext) -> ToolResult:
    title = args.get("coupon_title") or ""
    anonymous = args.get("anonymous_id") or "anonymous-demo"
    try:
        listing = ctx.http_content.get(
            "/api/v1/coupons", params={"venue_id": ctx.venue_id, "page_size": 20}).json()
    except httpx.HTTPError:
        return ToolResult(True, {"claimed": False, "message": "优惠服务暂不可用"},
                          error_code=2004, degraded=True)
    match = next((c for c in listing.get("items", []) if title and title in c["title"]), None)
    if not match:
        return ToolResult(True, {"claimed": False,
                                 "message": f"没找到「{title}」对应的券"}, degraded=True)
    if match.get("remaining", 0) <= 0:
        return ToolResult(True, {"claimed": False, "sold_out": True,
                                 "error_code": 4002,
                                 "message": "这张券已经领完了"}, degraded=True)
    try:
        resp = ctx.http_content.post(
            f"/api/v1/coupons/{match['id']}/claim",
            json={"anonymous_id": anonymous})
        body = resp.json()
    except httpx.HTTPError:
        return ToolResult(True, {"claimed": False, "message": "优惠服务暂不可用"},
                          error_code=2004, degraded=True)
    # 幂等重放也算"本次拿到券"（duplicate=true 回执无 id 键，PRD 契约 id?）
    claimed = resp.status_code == 200 and not body.get("error_code")
    out = {"claimed": claimed, "duplicate": bool(body.get("duplicate")),
           "coupon_id": match["id"], "title": match["title"]}
    if body.get("error_code") == 4002:
        out.update({"claimed": False, "sold_out": True, "error_code": 4002,
                    "message": "这张券已经领完了"})
    return ToolResult(True, out)
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
    """M7 不可用时降级：按候选顺序查 M8 出参，以同层距离排序（无位置保序）。"""
    ids = [int(i) for i in (args.get("candidates") or [])]
    if not ids:
        return ToolResult(True, {"ranked": []})
    try:
        items = []
        for pid in ids:
            resp = ctx.http_content.get(f"/api/v1/pois/{pid}",
                                        params={"venue_id": ctx.venue_id})
            body = resp.json()
            items.append({"poi_id": body["id"], "name": body["name"],
                          "floor": body.get("floor_id"),
                          "position_x": body.get("position_x"),
                          "position_y": body.get("position_y"),
                          "hot_score": 0})
    except httpx.HTTPError:
        return ToolResult(True, {"ranked": []})
    pos = ctx.position or {}
    px, py = pos.get("x", 600.0), pos.get("y", 400.0)
    here = pos.get("floor_id")

    def dist(it):
        if it["position_x"] is None or it["floor"] is None or here is None:
            return 1e9
        # 跨层加固定惩罚仍参与排序（审计：跨层曾完全不可见/并列时随机）
        plane = ((float(it["position_x"]) - px) ** 2
                 + (float(it["position_y"]) - py) ** 2) ** 0.5
        return plane + (500.0 if it["floor"] != here else 0.0)

    items.sort(key=dist)
    ranked = [{"poi_id": it["poi_id"], "name": it["name"], "floor": it["floor"],
               "score": round(1.0 / (1.0 + dist(it) / 100.0), 4),
               "reasons": ["距你较近"]} for it in items]
    return ToolResult(True, {"ranked": ranked, "temporary": True})
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
    except Exception as exc:
        return ToolResult(False, {"message": f"数据访问失败：{exc}"},
                          error_code=9999, degraded=True)


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


