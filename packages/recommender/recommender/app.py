"""M7 推荐服务：POST /recommend/rank（特征装配 → 纯内核打分 → 日志落库）。

python -m uvicorn recommender.app:app --port 8944
出参 {ranked: [{poi_id, name, score, factors, reasons}]}；候选空返回空列表
（PRD 8.5，不报错）。每条打分写 recommend_logs（message_id 可空）。
"""

from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

import psycopg
from fastapi import FastAPI
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from .features import gather
from .scoring import LoadableWeights, score_candidates


class RankRequest(BaseModel):
    tenant_id: int
    venue_id: int
    candidates: list[int] = Field(default_factory=list)
    position: dict = Field(default_factory=dict)   # {x, y, floor_id}
    tags: list[str] = Field(default_factory=list)
    promotion_poi_ids: list[int] = Field(default_factory=list)
    message_id: int | None = None
    trace_id: str | None = None


def create_app(dsn: str) -> FastAPI:
    app = FastAPI(title="recommender", version="0.1.0")

    @app.get("/health")
    def health() -> dict:
        return {"ok": True}

    @app.post("/recommend/rank")
    def rank(req: RankRequest):
        if not req.candidates:
            return {"ranked": []}
        weights = LoadableWeights.default()
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "select timezone from venues where id=%s and tenant_id=%s",
                (req.venue_id, req.tenant_id))
            vrow = cur.fetchone()
            if not vrow:
                return {"error_code": 1003, "message": "场地不属于当前租户"}
            now = _now(vrow[0])
            cands = gather(cur, req.tenant_id, req.venue_id, req.candidates,
                           req.position, now)
        promo = set(req.promotion_poi_ids)
        for c in cands:
            c["has_promotion"] = c["poi_id"] in promo
        ranked = score_candidates(cands, {"tags": req.tags}, weights=weights)
        for row in ranked:
            row["score"] = round(row["score"], 4)
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.executemany(
                "insert into recommend_logs (tenant_id, venue_id, message_id, "
                "poi_id, score, factors, reasons, rank) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s)",
                [(req.tenant_id, req.venue_id, req.message_id, r["poi_id"],
                  r["score"], Jsonb(r["factors"]), Jsonb(r["reasons"]), i)
                 for i, r in enumerate(ranked, start=1)])
        return {"ranked": ranked}

    return app


def _now(timezone: str) -> datetime:
    """真实时钟；SAGE_TIME_OVERRIDE（ISO 格式）为配置化时间注入点（测试/演示用）。"""
    override = os.environ.get("SAGE_TIME_OVERRIDE", "")
    if override:
        return datetime.fromisoformat(override)
    try:
        return datetime.now(ZoneInfo(timezone))
    except Exception:
        return datetime.now()


def make_app() -> FastAPI:
    """uvicorn 入口：DSN 全部来自环境变量（配置外置）。"""
    return create_app(os.environ["DATABASE_URL"].replace(
        "postgresql+psycopg://", "postgresql://", 1))
