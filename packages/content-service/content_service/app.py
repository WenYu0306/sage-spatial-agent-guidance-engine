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

import psycopg
from fastapi import Depends, FastAPI, Query
from platform_core.auth_router import (
    AuthContext,
    AuthRuntime,
    create_auth_router,
    install_error_handlers,
)
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _open_now(bh: dict, now: dt.datetime) -> bool:
    today = now.strftime("%a").lower()[:3]
    for span in (bh or {}).get(today) or []:
        try:
            start, end = span.split("-")
            if (dt.time.fromisoformat(start) <= now.time()
                    <= dt.time.fromisoformat(end)):
                return True
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


def create_app(dsn: str) -> FastAPI:
    runtime = AuthRuntime(dsn=dsn)
    app = FastAPI(title="content-service", version="0.1.0")
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
    def categories(ctx: AuthContext = Depends(runtime.dependency())):
        data = rows(
            "select code, name, parent_code, is_facility, searchable_by_ai "
            "from poi_categories where tenant_id=%s order by sort_order, code",
            (ctx.tenant_id,))
        return {"items": [{"code": r[0], "name": r[1], "parent_code": r[2],
                           "is_facility": r[3], "searchable_by_ai": r[4]}
                          for r in data]}

    @app.get("/api/v1/pois")
    def pois(
        ctx: AuthContext = Depends(runtime.dependency()),
        venue_id: int | None = None,
        floor_id: int | None = None,
        category_code: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
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
            where.append("p.category_code=%s")
            params.append(category_code)
        if status:
            where.append("p.status=%s")
            params.append(status)
        if keyword:
            where.append("(p.name ilike %s or p.intro ilike %s)")
            params.extend([f"%{keyword}%", f"%{keyword}%"])
        if merchant_id is not None:
            if ctx.merchant_id is not None and merchant_id != ctx.merchant_id:

                ctx.ensure_merchant(merchant_id)  # merchant 只能查自己门店
            where.append("p.merchant_id=%s")
            params.append(merchant_id)
        base = ("from pois p where " + " and ".join(where))
        if open_now:
            bh_rows = rows("select id, business_hours from pois p " + base,
                           tuple(params))
            now = dt.datetime.now()
            keep = {r[0] for r in bh_rows
                    if _open_now(r[1] if isinstance(r[1], dict) else {}, now)}
            if not keep:
                return {"items": [], "total": 0}
            base += f" and p.id in ({','.join(map(str, sorted(keep)))})"
        total = one("select count(*) " + base, tuple(params))[0]
        data = rows(
            "select p.id, p.name, p.category_code, p.floor_id, p.merchant_id, "
            "p.position_x, p.position_y, p.status, p.tags, p.intro " + base +
            " order by p.id limit %s offset %s",
            tuple(params) + (page_size, (page - 1) * page_size))
        return {"items": [{"id": r[0], "name": r[1], "category_code": r[2],
                           "floor_id": r[3], "merchant_id": r[4],
                           "position_x": float(r[5]), "position_y": float(r[6]),
                           "status": r[7], "tags": r[8], "intro": r[9]}
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

    @app.get("/api/v1/pois/{poi_id}")
    def poi_detail(poi_id: int, ctx: AuthContext = Depends(runtime.dependency())):
        row = one(
            "select p.id, p.name, p.intro, p.category_code, p.floor_id, "
            "p.business_hours, p.tags, p.images, p.contact, p.status, "
            "p.position_x, p.position_y, p.merchant_id, v.tenant_id "
            "from pois p join venues v on v.id=p.venue_id "
            "where p.id=%s and p.deleted_at is null", (poi_id,))
        if not row or row[13] != ctx.tenant_id:
            from platform_core.auth_router import AuthError

            raise AuthError(403, 1003, "POI 不存在或不属于当前租户")
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

    return app


def make_app() -> FastAPI:
    return create_app(os.environ["DATABASE_URL"].replace(
        "postgresql+psycopg://", "postgresql://", 1))
