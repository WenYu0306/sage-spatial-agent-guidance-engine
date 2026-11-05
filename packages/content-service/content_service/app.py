"""M8 内容服务（B1 只读层）：挂 M1 auth + PRD 7.3 空间内容只读端点。

python -m uvicorn content_service.app:make_app --factory --port 8945
范围规则（PRD 2.2/2.3）：token 携带 tenant_id/venue_id/merchant_id；
场地参数与 token 范围不符 → 403/1003；merchant 的 merchant_id 参数只接受
自己门店。错误码：401/1001 凭证、403/1003 越权、4001 状态不允许、
4002 已领完、4003 重复领取。
"""

from __future__ import annotations

import datetime as dt
import os
from typing import Literal

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from platform_core.auth_router import (
    AuthContext,
    AuthRuntime,
    create_auth_router,
    install_error_handlers,
)
from platform_core.events import track
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _open_now(bh: dict, now: dt.datetime) -> bool:
    """营业判定，支持跨天时段（22:00-02:00）。

    跨天段拆两半：今晚的前半夜（now>=start，挂今天条目）查得到；
    昨晚的后半夜（now<=end，挂昨天条目）也查得到。21:00 不会误判
    昨晚的跨天段（13.2 深测发现首版合并查的假阳性）。
    """
    t = now.time()
    today = now.strftime("%a").lower()[:3]
    yesterday = (now - dt.timedelta(days=1)).strftime("%a").lower()[:3]

    for span in (bh or {}).get(today) or []:
        try:
            start, end = span.split("-")
            start_t, end_t = dt.time.fromisoformat(start), dt.time.fromisoformat(end)
            if start_t <= end_t:
                if start_t <= t <= end_t:
                    return True
            elif t >= start_t:
                return True  # 今晚跨天段的前半夜
        except ValueError:
            continue

    for span in (bh or {}).get(yesterday) or []:
        try:
            start, end = span.split("-")
            start_t, end_t = dt.time.fromisoformat(start), dt.time.fromisoformat(end)
            if start_t > end_t and t <= end_t:
                return True  # 昨晚跨天段的后半夜（凌晨）
        except ValueError:
            continue
    return False


class PublishBody(BaseModel):
    target: str


class PoiCreate(BaseModel):
    venue_id: int
    floor_id: int
    category_code: str
    name: str = Field(min_length=1, max_length=128)
    intro: str | None = None
    position_x: float
    position_y: float
    business_hours: dict = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    images: list = Field(default_factory=list)
    contact: str | None = None


class PoiPatch(BaseModel):
    name: str | None = None
    intro: str | None = None
    position_x: float | None = None
    position_y: float | None = None
    business_hours: dict | None = None
    tags: list[str] | None = None
    images: list | None = None
    contact: str | None = None
    category_code: str | None = None


class ActCreate(BaseModel):
    venue_id: int
    poi_id: int | None = None
    act_type: str
    title: str = Field(min_length=1, max_length=128)
    description: str | None = None
    start_at: dt.datetime
    end_at: dt.datetime
    rules: dict = Field(default_factory=dict)


class ActPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    start_at: dt.datetime | None = None
    end_at: dt.datetime | None = None
    rules: dict | None = None


class ClaimBody(BaseModel):
    anonymous_id: str = Field(min_length=1, max_length=64)


class RouteNodeIn(BaseModel):
    venue_id: int
    floor_id: int
    node_type: str = "waypoint"
    poi_id: int | None = None
    x: float
    y: float
    accessible: bool = True

class RouteEdgeIn(BaseModel):
    venue_id: int
    from_node_id: int
    to_node_id: int
    edge_type: str = "walk"
    distance_meter: float
    weight: float | None = None
    accessible: bool = True
    is_bidirectional: bool = True

class HeartbeatBody(BaseModel):
    """设备心跳（F-19/PRD 733）：仅 device 角色，整行更新天然幂等。"""

    status: Literal["online", "offline", "maintenance"] = "online"
    app_version: str | None = Field(default=None, max_length=32)


class DocCreate(BaseModel):
    venue_id: int
    poi_id: int | None = None
    doc_type: str
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)


class DocPatch(BaseModel):
    title: str | None = None
    content: str | None = None
    doc_type: str | None = None


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    display_name: str = Field(min_length=1, max_length=64)
    role: str
    password: str = Field(min_length=8)
    status: str = "active"
    store: str | None = None  # merchant 建号必填（审计 S-3）：锚点门店名绑定


class UserPatch(BaseModel):
    status: str | None = None
    display_name: str | None = None


def create_app(dsn: str) -> FastAPI:
    runtime = AuthRuntime(dsn=dsn)
    app = FastAPI(title="content-service", version="0.1.0")

    from platform_core.ratelimit import SlidingWindow

    claim_limiter = SlidingWindow(max_events=30, window_s=60)  # P2 审计 S-5
    app.include_router(create_auth_router(runtime))
    install_error_handlers(app)

    def rows(sql: str, params: tuple = ()) -> list[tuple]:
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def one(sql: str, params: tuple = ()):
        found = rows(sql, params)
        return found[0] if found else None

    def _venue_of_tenant(ctx: AuthContext, venue_id: int) -> None:
        """场地必须属于 token 租户，且在 token 场地范围内（PRD 2.3 案例 2）。"""
        row = one("select tenant_id from venues where id=%s", (venue_id,))
        if not row or row[0] != ctx.tenant_id:
            from platform_core.auth_router import AuthError

            raise AuthError(403, 1003, "场地不存在或不属于当前租户")
        ctx.ensure_venue(venue_id)

    @app.get("/health")
    def health() -> dict:
        return {"ok": True}

    @app.get("/api/v1/venues")
    def venues(ctx: AuthContext = Depends(runtime.dependency("platform_admin", "venue_admin"))):
        data = rows(
            "select id, name, venue_type, status, tenant_id from venues "
            "where tenant_id=%s order by id", (ctx.tenant_id,))
        return {"items": [{"id": r[0], "name": r[1], "venue_type": r[2],
                           "status": r[3], "tenant_id": r[4]} for r in data]}

    @app.get("/api/v1/venues/{venue_id}/floors")
    def venue_floors(venue_id: int,
                     ctx: AuthContext = Depends(runtime.dependency())):
        _venue_of_tenant(ctx, venue_id)
        data = rows(
            "select id, name, level, is_default from floors where venue_id=%s "
            "order by level", (venue_id,))
        return {"items": [{"id": r[0], "name": r[1], "level": r[2],
                           "is_default": r[3]} for r in data]}

    @app.get("/api/v1/floors/{floor_id}/map-layer")
    def map_layer(floor_id: int, ctx: AuthContext = Depends(runtime.dependency())):
        row = one(
            "select v.tenant_id, m.id, m.svg_url, m.width, m.height, m.scale_meter, "
            "m.version from map_layers m join floors f on f.id=m.floor_id "
            "join venues v on v.id=f.venue_id where m.floor_id=%s "
            "and m.status='published' order by m.version desc limit 1", (floor_id,))
        if not row or row[0] != ctx.tenant_id:
            from platform_core.auth_router import AuthError

            raise AuthError(403, 1003, "楼层不存在或不属于当前租户")
        return {"id": row[1], "svg_url": row[2], "width": float(row[3]),
                "height": float(row[4]), "scale_meter": float(row[5]),
                "version": row[6]}

    @app.get("/api/v1/categories")
    def categories(ctx: AuthContext = Depends(runtime.optional())):
        data = rows(
            "select code, name, parent_code, is_facility, searchable_by_ai "
            "from poi_categories where tenant_id=%s order by sort_order, code",
            (ctx.tenant_id,))
        return {"items": [{"code": r[0], "name": r[1], "parent_code": r[2],
                           "is_facility": r[3], "searchable_by_ai": r[4]}
                          for r in data]}

    @app.get("/api/v1/pois")
    def pois(
        ctx: AuthContext = Depends(runtime.optional()),
        venue_id: int | None = None,
        floor_id: int | None = None,
        category_code: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
        scene_tag: str | None = None,
        merchant_id: int | None = None,
        open_now: bool = False,
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
    ):
        where = ["p.tenant_id=%s", "p.deleted_at is null"]
        params: list = [ctx.tenant_id]
        if venue_id is not None:
            _venue_of_tenant(ctx, venue_id)
        if ctx.venue_id is not None:  # 场地角色强制本场地（PRD 2.2 数据范围）
            where.append("p.venue_id=%s")
            params.append(ctx.venue_id)
        if floor_id is not None:
            where.append("p.floor_id=%s")
            params.append(floor_id)
        if category_code:
            where.append("p.category_code = any(%s)")
            params.append(_expand_category(ctx.tenant_id, category_code))
        if "guest" in ctx.roles:
            where.append("p.status='published'")  # guest 只见已发布（M12）
        elif status:
            where.append("p.status=%s")
            params.append(status)
        if keyword:
            where.append("(p.name ilike %s or p.intro ilike %s)")
            params.extend([f"%{keyword}%", f"%{keyword}%"])
        if scene_tag:
            # 场景词与标签双向子串包含（D-029：自 M5 迁入，行为一致）
            where.append(
                "exists (select 1 from jsonb_array_elements_text(p.tags) t "
                "where t like '%%' || %s || '%%' or %s like '%%' || t || '%%')")
            params.extend([scene_tag, scene_tag])
        if merchant_id is not None:
            if ctx.merchant_id is not None and merchant_id != ctx.merchant_id:

                ctx.ensure_merchant(merchant_id)  # merchant 只能查自己门店
            where.append("p.merchant_id=%s")
            params.append(merchant_id)
        base = ("from pois p where " + " and ".join(where))
        if open_now:
            bh_rows = rows("select id, business_hours " + base, tuple(params))
            now = dt.datetime.now()
            # 未知营业时间（无任何星期条目）按"未知"保留，不因过滤消失（13.2 ③）
            keep = {
                r[0] for r in bh_rows
                if _open_now(r[1] if isinstance(r[1], dict) else {}, now)
                or not any((r[1] if isinstance(r[1], dict) else {}).get(d)
                           for d in ("mon", "tue", "wed", "thu",
                                     "fri", "sat", "sun"))
            }
            if not keep:
                return {"items": [], "total": 0}
            base += f" and p.id in ({','.join(map(str, sorted(keep)))})"
        total = one("select count(*) " + base, tuple(params))[0]
        data = rows(
            "select p.id, p.name, p.category_code, p.floor_id, p.merchant_id, "
            "p.position_x, p.position_y, p.status, p.tags, p.intro, "
            "p.hot_score, f.name " + base.replace("from pois p", "from pois p "
            "join floors f on f.id=p.floor_id") +
            " order by p.id limit %s offset %s",
            tuple(params) + (page_size, (page - 1) * page_size))
        return {"items": [{"id": r[0], "name": r[1], "category_code": r[2],
                           "floor_id": r[3], "merchant_id": r[4],
                           "position_x": float(r[5]), "position_y": float(r[6]),
                           "status": r[7], "tags": r[8], "intro": r[9],
                           "hot_score": float(r[10]), "floor": r[11]}
                          for r in data], "total": total, "page": page,
                "page_size": page_size}

    # ---------- 写路径（B2）：CRUD + 发布状态机 ----------

    POI_TRANSITIONS = {
        "draft": {"pending"},
        "pending": {"published", "draft"},
        "published": {"offline"},
        "offline": {"draft"},
    }
    POI_TARGET_ROLES = {  # 允许执行该流转的角色
        "pending": ("platform_admin", "venue_admin", "venue_editor", "merchant"),
        "published": ("platform_admin", "venue_admin"),
        "draft": ("platform_admin", "venue_admin", "venue_editor"),
        "offline": ("platform_admin", "venue_admin"),
    }




    def _load_poi_for_write(ctx: AuthContext, poi_id: int) -> tuple:
        """取 POI 并强制范围（场地角色须同场地；merchant 仅锚点门店自己）。"""
        row = one(
            "select p.id, p.venue_id, p.merchant_id, p.status, p.tenant_id "
            "from pois p where p.id=%s and p.deleted_at is null", (poi_id,))
        if not row or row[4] != ctx.tenant_id:
            from platform_core.auth_router import AuthError

            raise AuthError(403, 1003, "POI 不存在或不属于当前租户")
        ctx.ensure_venue(row[1])
        if ctx.merchant_id is not None and row[2] != ctx.merchant_id:
            from platform_core.auth_router import AuthError

            ctx._deny("你没有该门店的操作权限", "poi", poi_id)
        return row

    @app.post("/api/v1/pois")
    def poi_create(body: PoiCreate,
                   ctx: AuthContext = Depends(runtime.dependency(
                       "platform_admin", "venue_admin", "venue_editor", "merchant"))):
        _venue_of_tenant(ctx, body.venue_id)
        if not one("select 1 from floors where id=%s and venue_id=%s",
                   (body.floor_id, body.venue_id)):
            from platform_core.auth_router import AuthError

            raise AuthError(403, 1003, "楼层不属于该场地")
        merchant_id = ctx.merchant_id if ctx.merchant_id is not None else None
        row = one(
            "insert into pois (tenant_id, venue_id, floor_id, merchant_id, "
            "category_code, name, intro, position_x, position_y, business_hours, "
            "tags, images, contact, status) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'draft') "
            "returning id, status",
            (ctx.tenant_id, body.venue_id, body.floor_id, merchant_id,
             body.category_code, body.name, body.intro, body.position_x,
             body.position_y, Jsonb(body.business_hours), Jsonb(body.tags),
             Jsonb(body.images), body.contact))
        runtime.oplog(ctx.tenant_id, ctx.user_id, "create", "poi", row[0],
                      ctx.trace_id, ctx.ip)
        return {"id": row[0], "status": row[1]}

    @app.patch("/api/v1/pois/{poi_id}")
    def poi_patch(poi_id: int, body: PoiPatch,
                  ctx: AuthContext = Depends(runtime.dependency(
                      "platform_admin", "venue_admin", "venue_editor", "merchant"))):
        row = _load_poi_for_write(ctx, poi_id)
        sets, params = [], []
        for col in ("name", "intro", "position_x", "position_y", "contact",
                    "category_code"):
            val = getattr(body, col)
            if val is not None:
                sets.append(f"{col}=%s")
                params.append(val)
        for col in ("business_hours", "tags", "images"):
            val = getattr(body, col)
            if val is not None:
                sets.append(f"{col}=%s")
                params.append(Jsonb(val))
        if not sets:
            return {"id": poi_id, "status": row[3]}
        params.append(poi_id)
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(f"update pois set {', '.join(sets)}, updated_at=now() "
                        "where id=%s returning status", tuple(params))
            status = cur.fetchone()[0]
            conn.commit()
        runtime.oplog(ctx.tenant_id, ctx.user_id, "update", "poi", poi_id,
                      ctx.trace_id, ctx.ip,
                      diff={"fields": [s.split("=")[0] for s in sets]})
        return {"id": poi_id, "status": status}

    @app.delete("/api/v1/pois/{poi_id}")
    def poi_delete(poi_id: int,
                   ctx: AuthContext = Depends(runtime.dependency(
                       "platform_admin", "venue_admin", "venue_editor"))):
        _load_poi_for_write(ctx, poi_id)
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute("update pois set deleted_at=now() where id=%s", (poi_id,))
            conn.commit()
        runtime.oplog(ctx.tenant_id, ctx.user_id, "delete", "poi", poi_id,
                      ctx.trace_id, ctx.ip)
        return {"id": poi_id, "deleted": True}

    @app.post("/api/v1/pois/{poi_id}/publish")
    def poi_publish(poi_id: int, body: PublishBody,
                    ctx: AuthContext = Depends(runtime.dependency(
                        "platform_admin", "venue_admin", "venue_editor", "merchant"))):
        row = _load_poi_for_write(ctx, poi_id)
        current, target = row[3], body.target
        if target not in POI_TRANSITIONS.get(current, set()):
            from fastapi.responses import JSONResponse

            return JSONResponse(status_code=409, content={
                "error_code": 4001,
                "message": f"状态不允许：{current} 不能转到 {target}"})
        if ctx.roles and not set(ctx.roles) & set(POI_TARGET_ROLES[target]):

            ctx._deny("你没有该操作的权限", "poi", poi_id)
        extra = ", published_at=now()" if target == "published" else ""
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(f"update pois set status=%s{extra} where id=%s",
                        (target, poi_id))
            conn.commit()
        runtime.oplog(ctx.tenant_id, ctx.user_id, "publish", "poi", poi_id,
                      ctx.trace_id, ctx.ip, diff={"to": target})
        return {"id": poi_id, "status": target}

    @app.get("/api/v1/pois/nearest")
    def pois_nearest(
        ctx: AuthContext = Depends(runtime.optional()),
        venue_id: int = Query(...),
        category_code: str = Query(...),
        x: float | None = Query(None),
        y: float | None = Query(None),
        floor_id: int | None = Query(None),
        limit: int = Query(3, ge=1, le=20),
    ):
        """设施最近查询（D-029，M5 facility.nearest 迁移目标）。

        有位置：同层优先+距离升序（热度破平）；无位置：按热度，不声称同层。
        guest 仅 published。
        """
        where = ["p.tenant_id=%s", "p.deleted_at is null", "p.status='published'"]
        params: list = [ctx.tenant_id]
        vrow = one("select id, tenant_id from venues where id=%s and status='active'",
                   (venue_id,))
        if not vrow:
            raise HTTPException(status_code=401, detail="场地不存在或未开放")
        params = [vrow[1]]
        where = ["p.tenant_id=%s", "p.deleted_at is null", "p.status='published'"]
        where.append("p.venue_id=%s")
        params.append(venue_id)
        where.append("p.category_code = any(%s)")
        params.append(_expand_category(ctx.tenant_id, category_code))
        data = rows(
            "select p.id, p.name, p.floor_id, p.position_x, p.position_y, "
            "p.hot_score, f.name from pois p "
            "join floors f on f.id=p.floor_id where " + " and ".join(where),
            tuple(params))
        has_position = x is not None and y is not None and floor_id is not None
        items = []
        for r in data:
            same_floor = has_position and r[2] == floor_id
            dist = (((float(r[3]) - x) ** 2 + (float(r[4]) - y) ** 2) ** 0.5
                    if has_position and r[2] == floor_id else 1e9)
            items.append({"poi_id": r[0], "name": r[1], "floor": r[6],
                          "position_x": float(r[3]), "position_y": float(r[4]),
                          "hot_score": float(r[5]), "same_floor": same_floor,
                          "_d": dist})
        items.sort(key=(lambda i: (i["_d"], -i["hot_score"])) if has_position
                   else (lambda i: -i["hot_score"]))
        return {"items": [{k: v for k, v in i.items() if k != "_d"}
                          for i in items[:limit]]}

    def _expand_category(tenant_id: int, key: str) -> list:
        """分类解析+父类展开（自 M5 _resolve_category_codes 迁入）。

        key 可为英文 code 或中文 name（"火锅"→hotpot 及其子类；
        "餐厅"→restaurant 及全部子类）。无匹配时原样返回（调用方自担）。
        """
        row = one(
            "select code, parent_code from poi_categories "
            "where tenant_id=%s and (code=%s or name=%s)", (tenant_id, key, key))
        if not row:
            return [key]
        base = row[1] or row[0]  # 父类取自身并展开子类；子类取自身
        if row[1]:
            base = row[0]
        kids = rows(
            "select code from poi_categories where tenant_id=%s and (code=%s or parent_code=%s)",
            (tenant_id, base, base))
        return [r[0] for r in kids] or [key]

    @app.get("/api/v1/route-nodes")
    def route_nodes_list(
        ctx: AuthContext = Depends(runtime.optional()),
        venue_id: int = Query(...),
        poi_id: int | None = Query(None),
        floor_id: int | None = Query(None),
    ):
        """路网节点读（D-029：M5 目标解析的数据源；guest 可读）。"""
        where = ["n.tenant_id=%s", "n.venue_id=%s"]
        params: list = [ctx.tenant_id, venue_id]
        if poi_id is not None:
            where.append("n.poi_id=%s")
            params.append(poi_id)
        if floor_id is not None:
            where.append("n.floor_id=%s")
            params.append(floor_id)
        data = rows(
            "select n.id, n.node_type, n.poi_id, n.x, n.y, n.accessible, f.name "
            "from route_nodes n join floors f on f.id=n.floor_id "
            "where " + " and ".join(where) + " order by n.id",
            tuple(params))
        return {"items": [{"id": r[0], "node_type": r[1], "poi_id": r[2],
                           "x": float(r[3]), "y": float(r[4]),
                           "accessible": r[5], "floor": r[6]} for r in data]}

    @app.post("/api/v1/route-nodes")
    def route_node_create(body: RouteNodeIn,
                          ctx: AuthContext = Depends(runtime.dependency(
                              "platform_admin", "venue_admin", "venue_editor"))):
        ctx.ensure_venue(body.venue_id)
        nid = one(
            "insert into route_nodes (tenant_id, venue_id, floor_id, node_type, poi_id, "
            "x, y, accessible) values (%s, %s, %s, %s, %s, %s, %s, %s) returning id",
            (ctx.tenant_id, body.venue_id, body.floor_id, body.node_type,
             body.poi_id, body.x, body.y, body.accessible))[0]
        runtime.oplog(ctx.tenant_id, ctx.user_id, "create", "route_node", nid,
                      ctx.trace_id, ctx.ip)
        return {"id": nid}

    @app.get("/api/v1/route-edges")
    def route_edges_list(
        ctx: AuthContext = Depends(runtime.optional()),
        venue_id: int = Query(...),
        node_id: int | None = Query(None),
    ):
        sql = ("select e.id, e.from_node_id, e.to_node_id, e.edge_type, "
               "e.distance_meter, e.weight, e.accessible, e.is_bidirectional "
               "from route_edges e where e.tenant_id=%s and e.venue_id=%s")
        params: list = [ctx.tenant_id, venue_id]
        if node_id is not None:
            sql += " and (e.from_node_id=%s or e.to_node_id=%s)"
            params.extend([node_id, node_id])
        data = rows(sql + " order by e.id", tuple(params))
        return {"items": [{"id": r[0], "from_node_id": r[1], "to_node_id": r[2],
                           "edge_type": r[3], "distance_meter": float(r[4]),
                           "weight": float(r[5]) if r[5] is not None else None,
                           "accessible": r[6], "bidirectional": r[7]} for r in data]}

    @app.post("/api/v1/route-edges")
    def route_edge_create(body: RouteEdgeIn,
                          ctx: AuthContext = Depends(runtime.dependency(
                              "platform_admin", "venue_admin", "venue_editor"))):
        ctx.ensure_venue(body.venue_id)
        weight = body.weight if body.weight is not None else body.distance_meter / 1.2
        eid = one(
            "insert into route_edges (tenant_id, venue_id, from_node_id, to_node_id, "
            "edge_type, distance_meter, weight, accessible, is_bidirectional) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s, %s) returning id",
            (ctx.tenant_id, body.venue_id, body.from_node_id, body.to_node_id,
             body.edge_type, body.distance_meter, weight, body.accessible,
             body.is_bidirectional))[0]
        runtime.oplog(ctx.tenant_id, ctx.user_id, "create", "route_edge", eid,
                      ctx.trace_id, ctx.ip)
        return {"id": eid}

    @app.get("/api/v1/pois/{poi_id}")
    def poi_detail(poi_id: int, ctx: AuthContext = Depends(runtime.optional())):
        row = one(
            "select p.id, p.name, p.intro, p.category_code, p.floor_id, "
            "p.business_hours, p.tags, p.images, p.contact, p.status, "
            "p.position_x, p.position_y, p.merchant_id, v.tenant_id "
            "from pois p join venues v on v.id=p.venue_id "
            "where p.id=%s and p.deleted_at is null", (poi_id,))
        if not row or row[13] != ctx.tenant_id:
            from platform_core.auth_router import AuthError

            raise AuthError(403, 1003, "POI 不存在或不属于当前租户")
        if "guest" in ctx.roles and row[9] != "published":
            from platform_core.auth_router import AuthError

            raise AuthError(403, 1003, "POI 不存在或不属于当前租户")  # guest 仅发布态
        acts = rows(
            "select id, title, act_type, start_at, end_at from activities "
            "where poi_id=%s and tenant_id=%s and status='active' "
            "and deleted_at is null order by id", (poi_id, ctx.tenant_id))
        cps = rows(
            "select id, title, coupon_type, threshold, value, total_qty, "
            "claimed_qty from coupons where poi_id=%s and tenant_id=%s "
            "and status='active' and deleted_at is null and end_at > now()",
            (poi_id, ctx.tenant_id))
        return {"id": row[0], "name": row[1], "intro": row[2],
                "category_code": row[3], "floor_id": row[4],
                "business_hours": row[5], "tags": row[6], "images": row[7],
                "contact": row[8], "status": row[9],
                "position_x": float(row[10]), "position_y": float(row[11]),
                "merchant_id": row[12],
                "activities": [{"id": a[0], "title": a[1], "act_type": a[2],
                                "start_at": a[3].isoformat(), "end_at": a[4].isoformat()}
                               for a in acts],
                "coupons": [{"id": c[0], "title": c[1], "coupon_type": c[2],
                             "threshold": float(c[3]), "value": float(c[4]),
                             "remaining": c[5] - c[6]} for c in cps]}

    # ---------- B3：活动状态机 / 领券幂等 / 知识文档 ----------

    ACT_TRANSITIONS = {
        "draft": {"pending"},
        "pending": {"active", "draft"},
        "active": {"ended"},
        "ended": {"archived"},
    }
    ACT_TARGET_ROLES = {
        "pending": ("platform_admin", "venue_admin", "venue_editor", "merchant"),
        "active": ("platform_admin", "venue_admin"),
        "ended": ("platform_admin", "venue_admin"),
        "archived": ("platform_admin", "venue_admin"),
    }

    def _load_act_for_write(ctx: AuthContext, act_id: int) -> tuple:
        row = one(
            "select id, venue_id, poi_id, status, tenant_id from activities "
            "where id=%s and deleted_at is null", (act_id,))
        if not row or row[4] != ctx.tenant_id:
            from platform_core.auth_router import AuthError

            raise AuthError(403, 1003, "活动不存在或不属于当前租户")
        ctx.ensure_venue(row[1])
        if "merchant" in ctx.roles:
            # 审计 S-4 归属校验：商户只能操作自己锚点门店的活动
            from platform_core.auth_router import AuthError

            own = one(
                "select 1 from pois where id=%s and merchant_id=%s",
                (row[2], ctx.merchant_id))
            if not own:
                raise AuthError(403, 1003, "活动不属于当前商户")
        return row

    @app.get("/api/v1/activities")
    def act_list(ctx: AuthContext = Depends(runtime.optional()),
                 act_type: str | None = None, status: str | None = None,
                 poi_id: int | None = None, title: str | None = None,
                 page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
        where = ["tenant_id=%s", "deleted_at is null"]
        params: list = [ctx.tenant_id]
        if ctx.venue_id is not None:
            where.append("venue_id=%s")
            params.append(ctx.venue_id)
        if act_type:
            where.append("act_type=%s")
            params.append(act_type)
        if "guest" in ctx.roles:
            where.append("status='published'")  # guest 只见已发布（M12，回归审计 S-1）
        elif status:
            where.append("status=%s")
            params.append(status)
        if poi_id is not None:
            where.append("poi_id=%s")
            params.append(poi_id)
        if title:
            where.append("title ilike %s")
            params.append(f"%{title}%")
        base = "from activities where " + " and ".join(where)
        total = one("select count(*) " + base, tuple(params))[0]
        data = rows("select id, venue_id, poi_id, act_type, title, status, "
                    "start_at, end_at " + base + " order by id desc limit %s offset %s",
                    tuple(params) + (page_size, (page - 1) * page_size))
        return {"items": [{"id": r[0], "venue_id": r[1], "poi_id": r[2],
                           "act_type": r[3], "title": r[4], "status": r[5],
                           "start_at": r[6].isoformat(), "end_at": r[7].isoformat()}
                          for r in data], "total": total}

    @app.post("/api/v1/activities")
    def act_create(body: ActCreate,
                   ctx: AuthContext = Depends(runtime.dependency(
                       "platform_admin", "venue_admin", "venue_editor", "merchant"))):
        _venue_of_tenant(ctx, body.venue_id)
        if ctx.merchant_id is not None:
            # merchant 只能建自己门店的活动；无门店归属的商场级活动不可建
            from platform_core.auth_router import AuthError

            if body.poi_id != ctx.merchant_id:
                raise AuthError(403, 1003, "商户只能创建自己门店的活动")
        elif body.poi_id is not None:
            if not one("select 1 from pois where id=%s and tenant_id=%s",
                       (body.poi_id, ctx.tenant_id)):
                from platform_core.auth_router import AuthError

                raise AuthError(403, 1003, "活动门店不属于当前租户")
        aid = one(
            "insert into activities (tenant_id, venue_id, poi_id, act_type, title, "
            "description, start_at, end_at, rules, status, created_by) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'draft', %s) returning id",
            (ctx.tenant_id, body.venue_id, body.poi_id, body.act_type, body.title,
             body.description, body.start_at, body.end_at, Jsonb(body.rules),
             ctx.user_id))[0]
        runtime.oplog(ctx.tenant_id, ctx.user_id, "create", "activity", aid,
                      ctx.trace_id, ctx.ip)
        return {"id": aid, "status": "draft"}

    @app.patch("/api/v1/activities/{act_id}")
    def act_patch(act_id: int, body: ActPatch,
                  ctx: AuthContext = Depends(runtime.dependency(
                      "platform_admin", "venue_admin", "venue_editor", "merchant"))):
        _load_act_for_write(ctx, act_id)
        sets, params = [], []
        for col in ("title", "description", "start_at", "end_at"):
            val = getattr(body, col)
            if val is not None:
                sets.append(f"{col}=%s")
                params.append(val)
        if body.rules is not None:
            sets.append("rules=%s")
            params.append(Jsonb(body.rules))
        if not sets:
            return {"id": act_id}
        params.append(act_id)
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(f"update activities set {', '.join(sets)}, updated_at=now() "
                        "where id=%s", tuple(params))
            conn.commit()
        runtime.oplog(ctx.tenant_id, ctx.user_id, "update", "activity", act_id,
                      ctx.trace_id, ctx.ip)
        return {"id": act_id}

    @app.post("/api/v1/activities/{act_id}/publish")
    def act_publish(act_id: int, body: PublishBody,
                    ctx: AuthContext = Depends(runtime.dependency(
                        "platform_admin", "venue_admin", "venue_editor", "merchant"))):
        row = _load_act_for_write(ctx, act_id)
        current, target = row[3], body.target
        if target not in ACT_TRANSITIONS.get(current, set()):
            from fastapi.responses import JSONResponse

            return JSONResponse(status_code=409, content={
                "error_code": 4001,
                "message": f"状态不允许：{current} 不能转到 {target}"})
        if not set(ctx.roles) & set(ACT_TARGET_ROLES[target]):

            ctx._deny("你没有该操作的权限", "activity", act_id)
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute("update activities set status=%s, updated_at=now() "
                        "where id=%s", (target, act_id))
            conn.commit()
        runtime.oplog(ctx.tenant_id, ctx.user_id, "publish", "activity", act_id,
                      ctx.trace_id, ctx.ip, diff={"to": target})
        return {"id": act_id, "status": target}

    @app.get("/api/v1/coupons")
    def coupon_list(ctx: AuthContext = Depends(runtime.optional())):
        where = ["c.tenant_id=%s", "c.deleted_at is null"]
        params: list = [ctx.tenant_id]
        if ctx.venue_id is not None:
            where.append("c.venue_id=%s")
            params.append(ctx.venue_id)
        data = rows(
            "select c.id, c.title, c.coupon_type, c.threshold, c.value, "
            "c.total_qty - c.claimed_qty, c.poi_id, c.start_at, c.end_at, p.name "
            "from coupons c left join pois p on p.id = c.poi_id "
            "where " + " and ".join(where) + " order by c.id",
            tuple(params))
        return {"items": [{"id": r[0], "title": r[1], "coupon_type": r[2],
                           "threshold": float(r[3]), "value": float(r[4]),
                           "remaining": r[5], "poi_id": r[6],
                           "poi_name": r[9],
                           "start_at": r[7].isoformat(), "end_at": r[8].isoformat()}
                          for r in data]}

    @app.post("/api/v1/coupons/{coupon_id}/claim")
    def coupon_claim(coupon_id: int, body: ClaimBody, request: Request):
        """guest 领券（无登录，anonymous_id 标识）。幂等键 coupon_id:anonymous_id；
        库存原子扣减（禁止先查后写，PRD 12）；重放返回既有券 duplicate=true。
        领取限流（P2 审计 S-5）：anonymous_id+IP 30 次/分钟。
        """
        ip = request.client.host if request.client else "anon"
        if not claim_limiter.allow(ip):  # 按IP：换 anonymous_id 横向扫 ID 也拦（审计 S-5）
            from fastapi.responses import JSONResponse

            return JSONResponse(status_code=429, content={
                "error_code": 9002, "message": "领取过于频繁"})
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "update coupons set claimed_qty = claimed_qty + 1 "
                "where id=%s and status='active' and deleted_at is null "
                "and claimed_qty < total_qty and start_at <= now() "
                "and end_at > now() returning id", (coupon_id,))
            if cur.fetchone() is None:
                conn.rollback()
                cur.execute("select 1 from coupon_claims where idempotency_key=%s",
                            (f"{coupon_id}:{body.anonymous_id}",))
                if cur.fetchone():
                    return {"coupon_id": coupon_id, "duplicate": True}
                return {"error_code": 4002, "message": "这张券已经领完了"}
            try:
                cur.execute(
                    "insert into coupon_claims (tenant_id, coupon_id, anonymous_id, "
                    "idempotency_key) values ((select tenant_id from coupons "
                    "where id=%s), %s, %s, %s) returning id",
                    (coupon_id, coupon_id, body.anonymous_id,
                     f"{coupon_id}:{body.anonymous_id}"))
                claim_id = cur.fetchone()[0]
                conn.commit()
            except psycopg.errors.UniqueViolation:
                conn.rollback()  # 回滚已撤销本次 +1，无需再补偿（防止双重回冲）
                return {"coupon_id": coupon_id, "duplicate": True}
        return {"id": claim_id, "coupon_id": coupon_id, "duplicate": False}

    @app.get("/api/v1/knowledge-documents")
    def doc_list(ctx: AuthContext = Depends(runtime.dependency(
                     "platform_admin", "venue_admin", "venue_editor")),
                 title: str | None = None, doc_type: str | None = None,
                 page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
        where = ["tenant_id=%s"]
        params: list = [ctx.tenant_id]
        if ctx.venue_id is not None:
            where.append("venue_id=%s")
            params.append(ctx.venue_id)
        if title:
            where.append("title ilike %s")
            params.append(f"%{title}%")
        if doc_type:
            where.append("doc_type=%s")
            params.append(doc_type)
        base = "from knowledge_documents where " + " and ".join(where)
        total = one("select count(*) " + base, tuple(params))[0]
        data = rows("select id, venue_id, poi_id, doc_type, title, status, "
                    "version " + base + " order by id limit %s offset %s",
                    tuple(params) + (page_size, (page - 1) * page_size))
        return {"items": [{"id": r[0], "venue_id": r[1], "poi_id": r[2],
                           "doc_type": r[3], "title": r[4], "status": r[5],
                           "version": r[6]} for r in data], "total": total}

    @app.get("/api/v1/knowledge-documents/{doc_id}")
    def doc_detail(doc_id: int,
                   ctx: AuthContext = Depends(runtime.dependency(
                       "platform_admin", "venue_admin", "venue_editor"))):
        row = one(
            "select id, venue_id, poi_id, doc_type, title, content, status, version "
            "from knowledge_documents where id=%s and tenant_id=%s",
            (doc_id, ctx.tenant_id))
        if not row:
            from platform_core.auth_router import AuthError

            raise AuthError(403, 1003, "文档不存在或不属于当前租户")
        return {"id": row[0], "venue_id": row[1], "poi_id": row[2], "doc_type": row[3],
                "title": row[4], "content": row[5], "status": row[6], "version": row[7]}

    @app.post("/api/v1/knowledge-documents")
    def doc_create(body: DocCreate,
                   ctx: AuthContext = Depends(runtime.dependency(
                       "platform_admin", "venue_admin", "venue_editor"))):
        _venue_of_tenant(ctx, body.venue_id)
        did = one(
            "insert into knowledge_documents (tenant_id, venue_id, poi_id, "
            "doc_type, title, content) values (%s, %s, %s, %s, %s, %s) "
            "returning id",
            (ctx.tenant_id, body.venue_id, body.poi_id, body.doc_type,
             body.title, body.content))[0]
        runtime.oplog(ctx.tenant_id, ctx.user_id, "create", "knowledge_document",
                      did, ctx.trace_id, ctx.ip)
        return {"id": did, "version": 1}

    @app.patch("/api/v1/knowledge-documents/{doc_id}")
    def doc_patch(doc_id: int, body: DocPatch,
                  ctx: AuthContext = Depends(runtime.dependency(
                      "platform_admin", "venue_admin", "venue_editor"))):
        row = one("select id, tenant_id from knowledge_documents where id=%s",
                  (doc_id,))
        if not row or row[1] != ctx.tenant_id:
            from platform_core.auth_router import AuthError

            raise AuthError(403, 1003, "文档不存在或不属于当前租户")
        sets, params = [], []
        for col in ("title", "content", "doc_type"):
            val = getattr(body, col)
            if val is not None:
                sets.append(f"{col}=%s")
                params.append(val)
        if not sets:
            return {"id": doc_id}
        params.append(doc_id)
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(f"update knowledge_documents set {', '.join(sets)}, "
                        "version=version+1, updated_at=now() where id=%s "
                        "returning version", tuple(params))
            version = cur.fetchone()[0]
            conn.commit()
        runtime.oplog(ctx.tenant_id, ctx.user_id, "update", "knowledge_document",
                      doc_id, ctx.trace_id, ctx.ip)
        return {"id": doc_id, "version": version}

    @app.delete("/api/v1/knowledge-documents/{doc_id}")
    def doc_delete(doc_id: int,
                   ctx: AuthContext = Depends(runtime.dependency(
                       "platform_admin", "venue_admin", "venue_editor"))):
        row = one("select id, tenant_id from knowledge_documents where id=%s",
                  (doc_id,))
        if not row or row[1] != ctx.tenant_id:
            from platform_core.auth_router import AuthError

            raise AuthError(403, 1003, "文档不存在或不属于当前租户")
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute("delete from knowledge_documents where id=%s", (doc_id,))
            conn.commit()
        runtime.oplog(ctx.tenant_id, ctx.user_id, "delete", "knowledge_document",
                      doc_id, ctx.trace_id, ctx.ip)
        return {"id": doc_id, "deleted": True}

    # ---------- B4：设备列表（PRD 7.4）与账号管理（PRD 2.2） ----------

    @app.get("/api/v1/devices")
    def device_list(ctx: AuthContext = Depends(runtime.dependency(
            "platform_admin", "venue_admin"))):
        where = "where d.tenant_id=%s"
        params: list = [ctx.tenant_id]
        if ctx.venue_id is not None:
            where += " and d.venue_id=%s"
            params.append(ctx.venue_id)
        data = rows(
            "select d.id, d.code, d.name, d.device_type, d.status, "
            "d.last_seen_at, d.app_version, f.name " + f"from devices d "
            f"left join floors f on f.id=d.floor_id {where} order by d.id",
            tuple(params))
        return {"items": [{"id": r[0], "code": r[1], "name": r[2],
                           "device_type": r[3], "status": r[4],
                           "last_seen_at": r[5].isoformat() if r[5] else None,
                           "app_version": r[6], "floor": r[7]} for r in data]}

    @app.get("/api/v1/devices/me")
    def device_me(ctx: AuthContext = Depends(runtime.dependency("device"))):
        """设备身份自读（M11）：device_id 由 token 携带（devices.code == username 成对约定）。

        联表带出场地名/营业时间——PRD 16"设备只能拉取配置"的自读范围，不动 /venues 管理端点。
        """
        row = one(
            "select d.id, d.code, d.name, d.venue_id, d.status, d.app_version, "
            "d.last_seen_at, v.name, v.settings, d.floor_id, f.name, "
            "d.position_x, d.position_y "
            "from devices d join venues v on v.id = d.venue_id "
            "left join floors f on f.id = d.floor_id "
            "where d.id=%s and d.tenant_id=%s",
            (ctx.device_id, ctx.tenant_id))
        if not row:
            raise HTTPException(status_code=404,
                                detail="设备身份未登记（devices.code 须与用户名一致）")
        settings = row[8] or {}
        return {"data": {"device_id": row[0], "code": row[1], "name": row[2],
                         "venue_id": row[3], "status": row[4],
                         "app_version": row[5],
                         "last_seen_at": row[6].isoformat() if row[6] else None,
                         "venue_name": row[7],
                         "business_hours": settings.get("business_hours"),
                         "floor_id": row[9], "floor_name": row[10],
                         "position_x": float(row[11]) if row[11] is not None else None,
                         "position_y": float(row[12]) if row[12] is not None else None}}

    @app.post("/api/v1/devices/{device_id}/heartbeat")
    def device_heartbeat(device_id: int, body: HeartbeatBody,
                         ctx: AuthContext = Depends(runtime.dependency("device"))):
        """设备心跳（F-19/PRD 733）：更新 last_seen_at/status/app_version，打点 device_active。

        设备账号按 user_roles.venue_id 绑定场地——只能心跳本场地设备（跨场地 404）；
        且 device_id 必须等于 token 携带身份（同场地冒充他机 → 403，审计 S-5）。
        """
        if ctx.device_id is None or ctx.device_id != device_id:
            from platform_core.auth_router import AuthError

            raise AuthError(403, 1003, "设备身份与令牌不符")
        row = one(
            "update devices set last_seen_at=now(), status=%s, "
            "app_version=coalesce(%s, app_version) "
            "where id=%s and tenant_id=%s and venue_id=%s returning id",
            (body.status, body.app_version, device_id, ctx.tenant_id, ctx.venue_id))
        if not row:
            raise HTTPException(status_code=404, detail="设备不存在或不属于该场地")
        try:
            from platform_core.events import new_event_id

            track(dsn, {
                "event_id": new_event_id(),
                "tenant_id": ctx.tenant_id, "venue_id": ctx.venue_id,
                "event_type": "device_active", "actor_type": "device",
                "device_id": device_id,
                "payload": {"status": body.status,
                            "app_version": body.app_version},
            })
        except Exception:  # 打点失败不阻断心跳（遥测不破坏主链路）
            pass
        return {"data": {"device_id": device_id, "status": body.status,
                         "app_version": body.app_version}}

    @app.get("/api/v1/users")
    def user_list(ctx: AuthContext = Depends(runtime.dependency(
            "platform_admin", "venue_admin"))):
        data = rows(
            "select u.id, u.username, u.display_name, u.status, u.last_login_at, "
            "r.code, ur.venue_id, ur.merchant_id "
            "from users u left join user_roles ur on ur.user_id=u.id "
            "left join roles r on r.id=ur.role_id "
            "where u.tenant_id=%s order by u.id", (ctx.tenant_id,))
        merged: dict[int, dict] = {}
        for r in data:
            row = merged.setdefault(r[0], {
                "id": r[0], "username": r[1], "display_name": r[2],
                "status": r[3], "last_login_at": r[4].isoformat() if r[4] else None,
                "roles": []})
            if r[5]:
                row["roles"].append(r[5])
        return {"items": list(merged.values())}

    @app.post("/api/v1/users")
    def user_create(body: UserCreate,
                    ctx: AuthContext = Depends(runtime.dependency(
                        "platform_admin", "venue_admin"))):
        from platform_core.auth import hash_password
        from platform_core.auth_router import AuthError

        if not one("select 1 from roles where code=%s", (body.role,)):
            raise AuthError(403, 1003, "角色不存在")
        if body.role == "platform_admin" and "platform_admin" not in ctx.roles:
            raise AuthError(403, 1003, "仅平台管理员可创建平台管理员")  # 审计 S-3 提权拦截
        merchant_id = None
        if body.role == "merchant":
            if not body.store:
                raise AuthError(403, 1003, "merchant 建号必须绑定门店")  # 审计 S-3
            mrow = one(
                "select id from pois where tenant_id=%s and venue_id=%s and name=%s "
                "and deleted_at is null",
                (ctx.tenant_id, ctx.venue_id, body.store))
            if not mrow:
                raise AuthError(403, 1003, "绑定的门店不存在")
            merchant_id = mrow[0]
        if one("select 1 from users where tenant_id=%s and username=%s",
               (ctx.tenant_id, body.username)):
            raise AuthError(403, 1003, "用户名已存在")
        scope_venue = ctx.venue_id if body.role in (
            "venue_admin", "venue_editor", "device") else None
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "insert into users (tenant_id, username, password_hash, display_name, "
                "status) values (%s, %s, %s, %s, %s) returning id",
                (ctx.tenant_id, body.username, hash_password(body.password),
                 body.display_name, body.status))
            uid = cur.fetchone()[0]
            cur.execute(
                "insert into user_roles (user_id, role_id, venue_id, merchant_id) "
                "values (%s, (select id from roles where code=%s), %s, %s)",
                (uid, body.role, scope_venue, merchant_id))
            conn.commit()
        runtime.oplog(ctx.tenant_id, ctx.user_id, "create", "user", uid,
                      ctx.trace_id, ctx.ip, diff={"role": body.role})
        return {"id": uid, "status": body.status}

    @app.patch("/api/v1/users/{user_id}")
    def user_patch(user_id: int, body: UserPatch,
                   ctx: AuthContext = Depends(runtime.dependency(
                       "platform_admin", "venue_admin"))):
        row = one("select id from users where id=%s and tenant_id=%s",
                  (user_id, ctx.tenant_id))
        if not row:
            from platform_core.auth_router import AuthError

            raise AuthError(403, 1003, "账号不存在或不属于当前租户")
        sets, params = [], []
        if body.status is not None:
            sets.append("status=%s")
            params.append(body.status)
        if body.display_name is not None:
            sets.append("display_name=%s")
            params.append(body.display_name)
        if not sets:
            return {"id": user_id}
        params.append(user_id)
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(f"update users set {', '.join(sets)}, updated_at=now() "
                        "where id=%s returning status", tuple(params))
            status = cur.fetchone()[0]
            conn.commit()
        runtime.oplog(ctx.tenant_id, ctx.user_id, "update", "user", user_id,
                      ctx.trace_id, ctx.ip, diff={"status": status})
        return {"id": user_id, "status": status}

    return app


def make_app() -> FastAPI:
    return create_app(os.environ["DATABASE_URL"].replace(
        "postgresql+psycopg://", "postgresql://", 1))
