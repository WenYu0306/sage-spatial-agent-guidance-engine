"""M9 analytics-service：埋点接收（PRD 7.4）+ 指标聚合（PRD 15 节 11 指标）。

python -m uvicorn analytics_service.app:make_app --factory --port 8946
读路径即时聚合 events 表（D-025：metrics_daily 留 V2 预聚合）；token 与
content-service 同签发方（同 JWT_SECRET），范围注入复用 M1 AuthRuntime。
"""

from __future__ import annotations

import datetime as dt
import os
import zoneinfo

import psycopg
from fastapi import Depends, FastAPI, Query, Request
from platform_core.auth_router import (
    AuthContext,
    AuthRuntime,
    create_auth_router,
    install_error_handlers,
)
from platform_core.events import track_batch
from pydantic import BaseModel, Field

METRIC_CODES = (
    "ai_query_count", "search_keyword_top", "poi_search_rank", "route_plan_count",
    "hot_destination_top", "poi_recommend_count", "coupon_claim_count",
    "coupon_use_count", "device_usage_count", "traffic_by_hour", "handover_rate",
)
_COUNT_EVENT = {  # 计数型指标 → 事件类型
    "ai_query_count": "ai_query",
    "route_plan_count": "route_plan",
    "coupon_claim_count": "coupon_claim",
    "coupon_use_count": "coupon_use",
    "device_usage_count": "device_active",
    "poi_recommend_count": "poi_recommended",
}
_TOP_EVENT = {  # Top 榜指标 → (事件类型, 取值来源)
    "search_keyword_top": ("search", "payload->>'keyword'"),
    "poi_search_rank": ("search", "coalesce(subject_id::text, payload->>'poi_id')"),
    "hot_destination_top": ("poi_view", "coalesce(subject_id::text, payload->>'poi_id')"),
}


class EventsBody(BaseModel):
    events: list[dict] = Field(min_length=1)


def create_app(dsn: str) -> FastAPI:
    runtime = AuthRuntime(dsn=dsn)
    app = FastAPI(title="analytics-service", version="0.1.0")
    app.include_router(create_auth_router(runtime))
    install_error_handlers(app)

    from platform_core.ratelimit import SlidingWindow

    events_limiter = SlidingWindow(max_events=120, window_s=60)  # P2 审计 S-9

    def rows(sql: str, params: tuple = ()) -> list[tuple]:
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def _venue_where(ctx: AuthContext, table: str = "e") -> tuple[str, list]:
        where = [f"{table}.tenant_id=%s"]
        params: list = [ctx.tenant_id]
        if ctx.venue_id is not None:
            where.append(f"{table}.venue_id=%s")
            params.append(ctx.venue_id)
        return " and ".join(where), params

    def _venue_tz(ctx: AuthContext) -> zoneinfo.ZoneInfo:
        """场地时区（PRD venues.timezone）：日期边界/分桶以本地口径，缺省 UTC。"""
        if ctx.venue_id is not None:
            row = rows("select timezone from venues where id=%s", (ctx.venue_id,))
            name = row[0][0] if row and row[0][0] else None
            if name:
                try:
                    return zoneinfo.ZoneInfo(name)
                except zoneinfo.ZoneInfoNotFoundError:
                    pass
        return dt.timezone.utc

    @app.get("/health")
    def health() -> dict:
        return {"ok": True}

    @app.post("/api/v1/events")
    def post_events(request: Request, body: EventsBody):
        """guest/device 直报（PRD 7.4：全部含 device/guest）；幂等整批处理。

        防伪造（P2 审计 S-9）：tenant_id/venue_id/occurred_at 一律服务端裁定——
        有 token 按身份；guest 以 body 场地反查（须 active），租户自场地派生。
        """
        from fastapi.responses import JSONResponse

        ip = request.client.host if request.client else "anon"
        if not events_limiter.allow(ip):
            return JSONResponse(status_code=429, content={
                "error_code": 9002, "message": "请求过于频繁"})
        auth_header = request.headers.get("authorization", "")
        venue_ids = {e.get("venue_id") for e in body.events}
        if auth_header.startswith("Bearer "):
            ctx = runtime._authed_ctx(request)
        else:
            if len(venue_ids) != 1 or not all(isinstance(v, int) for v in venue_ids):
                return JSONResponse(status_code=422, content={
                    "error_code": 1001, "message": "guest 事件必须指向同一场地"})
            vrow = rows("select id, tenant_id from venues where id=%s and status='active'",
                        (venue_ids.pop(),))
            if not vrow:
                return JSONResponse(status_code=401, content={
                    "error_code": 1001, "message": "场地不存在或未开放"})
            from platform_core.auth_router import AuthContext

            ctx = AuthContext(user_id=0, tenant_id=vrow[0][1], roles=["guest"],
                              venue_id=vrow[0][0], merchant_id=None, device_id=None,
                              _runtime=runtime, ip=ip)
        now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
        for e in body.events:
            e["tenant_id"] = ctx.tenant_id
            e["venue_id"] = ctx.venue_id
            e["occurred_at"] = now_iso
        if len(body.events) > 50:
            return JSONResponse(status_code=422, content={
                "error_code": 1001, "message": "单次批量上限 50 条"})
        for ev in body.events:
            if ev.get("event_type") not in __import__(
                    "platform_core.events", fromlist=["EVENT_TYPES"]).EVENT_TYPES:
                from fastapi.responses import JSONResponse

                return JSONResponse(status_code=200, content={
                    "error_code": 1001,
                    "message": f"未知事件类型：{ev.get('event_type')}（PRD 15 字典）"})
        result = track_batch(dsn, body.events)
        return {**result, "received": len(body.events)}

    @app.get("/api/v1/metrics/codes")
    def metric_codes(ctx: AuthContext = Depends(runtime.dependency())):
        return {"codes": list(METRIC_CODES)}

    @app.get("/api/v1/metrics/overview")
    def overview(ctx: AuthContext = Depends(runtime.dependency(
                     "platform_admin", "venue_admin", "venue_editor")),
                 date_from: dt.date | None = None,
                 date_to: dt.date | None = None):
        where, params = _venue_where(ctx)
        tz = _venue_tz(ctx)
        if date_from:
            where += " and e.occurred_at >= %s"
            params.append(dt.datetime.combine(date_from, dt.time.min,
                                              tzinfo=tz).astimezone(dt.timezone.utc))
        if date_to:
            where += " and e.occurred_at < %s"
            params.append(dt.datetime.combine(date_to + dt.timedelta(days=1),
                                              dt.time.min,
                                              tzinfo=tz).astimezone(dt.timezone.utc))
        metrics: dict[str, float] = {}
        for code, ev in _COUNT_EVENT.items():
            row = rows(f"select count(*) from events e where {where} "
                       "and e.event_type=%s", tuple(params + [ev]))
            metrics[code] = row[0][0]
        handover = rows(f"select count(*) filter (where e.event_type='route_handover'), "
                        f"count(*) filter (where e.event_type='route_plan') "
                        f"from events e where {where}", tuple(params))[0]
        metrics["handover_rate"] = round(handover[0] / handover[1], 4) if handover[1] else 0.0
        traffic = rows(f"select count(*) from events e where {where} "
                       "and e.event_type in ('ai_query','search','poi_view')",
                       tuple(params))[0][0]
        metrics["traffic_by_hour"] = float(traffic)
        metrics["search_keyword_top"] = metrics["hot_destination_top"] = 0  # 榜单型见 /{code}
        return {"metrics": {k: v for k, v in metrics.items()
                            if not k.endswith("_top")}}

    @app.get("/api/v1/metrics/{code}")
    def metric_timeseries(code: str,
                          ctx: AuthContext = Depends(runtime.dependency(
                              "platform_admin", "venue_admin", "venue_editor")),
                          granularity: str = Query("day", pattern="^(day|hour)$"),
                          date_from: dt.date | None = None,
                          date_to: dt.date | None = None):
        from fastapi.responses import JSONResponse

        if code not in METRIC_CODES:
            return JSONResponse(status_code=200, content={
                "error_code": 1001, "message": f"未知指标 {code}（11 指标见 /metrics/codes）"})
        where, params = _venue_where(ctx)
        tzname = str(_venue_tz(ctx))
        bucket = ("date_trunc('day', e.occurred_at at time zone %s)" if granularity == "day"
                  else "date_trunc('hour', e.occurred_at at time zone %s)")
        if code in _COUNT_EVENT:
            data = rows(
                f"select {bucket} as b, count(*) from events e where {where} "
                "and e.event_type=%s group by b order by b",
                tuple([tzname] + params + [_COUNT_EVENT[code]]))
            return {"points": [{"date": str(r[0].date()), "value": r[1]} for r in data]}
        if code in _TOP_EVENT:
            ev, expr = _TOP_EVENT[code]
            data = rows(
                f"select {expr} as label, count(*) from events e where {where} "
                "and e.event_type=%s and coalesce("
                + expr + ", '') <> '' group by label order by count(*) desc limit 10",
                tuple(params + [ev]))  # top 榜无时间分桶，不涉 tz 占位
            return {"points": [{"label": r[0], "value": r[1]} for r in data]}
        if code == "handover_rate":
            data = rows(
                f"select {bucket} as b, "
                "count(*) filter (where e.event_type='route_handover'), "
                "count(*) filter (where e.event_type='route_plan') "
                f"from events e where {where} group by b order by b",
                tuple([tzname] + params))
            return {"points": [{"date": str(r[0].date()),
                                "value": round(r[1] / r[2], 4) if r[2] else 0.0}
                               for r in data]}
        # traffic_by_hour：问答+搜索+看详情 的逐时流量
        data = rows(
            f"select {bucket} as b, count(*) from events e where {where} "
            "and e.event_type in ('ai_query','search','poi_view') group by b order by b",
            tuple(params))
        return {"points": [{"date": str(r[0]), "value": r[1]} for r in data]}

    @app.get("/api/v1/metrics/merchant/{poi_id}")
    def merchant_metrics(poi_id: int,
                         ctx: AuthContext = Depends(runtime.dependency("merchant"))):
        ctx.ensure_merchant(poi_id)  # 商户只看自己门店引流（PRD 2.2）
        where, params = _venue_where(ctx)
        base = f"and {where} and (e.subject_id=%s or e.payload->>'poi_id'=%s)"
        args = tuple(params + [poi_id, str(poi_id)])

        def _count(ev: str) -> int:
            return rows(f"select count(*) from events e where e.event_type=%s {base}",
                        tuple([ev]) + args)[0][0]

        return {"poi_id": poi_id,
                "searched": _count("search"), "recommended": _count("poi_recommended"),
                "navigated": _count("route_plan"), "coupon_claimed": _count("coupon_claim")}

    return app


def make_app() -> FastAPI:
    return create_app(os.environ["DATABASE_URL"].replace(
        "postgresql+psycopg://", "postgresql://", 1))
