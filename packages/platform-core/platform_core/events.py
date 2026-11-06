"""M1 埋点 SDK：track/track_batch 写 events 表（event_id 幂等，PRD 15 事件字典）。

内核模块（M5 问答打点）与端层共用；event_type 白名单校验防止脏数据进指标。
"""

from __future__ import annotations

import datetime as dt
import uuid

import psycopg
from psycopg.types.json import Jsonb

# PRD 15 节事件字典（ai_query_failed 为字典附带的失败伴随类型）
EVENT_TYPES = frozenset({
    "ai_query", "ai_query_failed", "search", "poi_view", "poi_recommended",
    "route_plan", "route_handover", "coupon_claim", "coupon_use",
    "device_active", "ad_impression", "ad_click",
})

_INSERT = """
insert into events (tenant_id, venue_id, event_id, event_type, subject_type,
                    subject_id, actor_type, actor_id, device_id, floor_id,
                    session_id, payload, trace_id, occurred_at)
values (%(tenant_id)s, %(venue_id)s, %(event_id)s, %(event_type)s,
        %(subject_type)s, %(subject_id)s, %(actor_type)s, %(actor_id)s,
        %(device_id)s, %(floor_id)s, %(session_id)s, %(payload)s,
        %(trace_id)s, %(occurred_at)s)
on conflict (event_id) do nothing
returning id
"""


def _normalize(event: dict) -> dict:
    if event.get("event_type") not in EVENT_TYPES:
        raise ValueError(f"未知事件类型：{event.get('event_type')}（PRD 15 字典）")
    # 审查 blocking#7：event_id/actor_type 表级 NOT NULL 且无默认填充，
    # 缺失/非法曾直落 psycopg 500——统一前置校验，调用方转错误信封。
    event_id = event.get("event_id")
    if not isinstance(event_id, str) or not event_id or len(event_id) > 64:
        raise ValueError("event_id 必须为 ≤64 字符的非空字符串（幂等键）")
    actor_type = event.get("actor_type")
    if not isinstance(actor_type, str) or not actor_type or len(actor_type) > 16:
        raise ValueError("actor_type 必须为 ≤16 字符的非空字符串")
    filled = {
        "subject_type": None, "subject_id": None, "actor_id": None,
        "device_id": None, "floor_id": None, "session_id": None,
        "payload": {}, "trace_id": None,
        "occurred_at": dt.datetime.now(dt.timezone.utc),
    }
    filled.update(event)
    filled["payload"] = Jsonb(filled["payload"])
    return filled


def track(dsn: str, event: dict) -> dict:
    """单条埋点；event_id 冲突视为重放，返回 duplicate=True（不报错）。"""
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(_INSERT, _normalize(event))
        row = cur.fetchone()
        conn.commit()
    if row:
        return {"id": row[0], "duplicate": False}
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("select id from events where event_id=%s",
                    (event["event_id"],))
        return {"id": cur.fetchone()[0], "duplicate": True}


def track_batch(dsn: str, events: list[dict], *, max_batch: int = 50) -> dict:
    """批量埋点（≤50，PRD 7.4）：幂等跳过，返回 inserted/skipped 计数。"""
    if len(events) > max_batch:
        raise ValueError(f"单次批量上限 {max_batch} 条（PRD 7.4），收到 {len(events)}")
    inserted = skipped = 0
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        for event in events:
            cur.execute(_INSERT, _normalize(event))
            if cur.fetchone():
                inserted += 1
            else:
                skipped += 1
        conn.commit()
    return {"inserted": inserted, "skipped": skipped}


def new_event_id() -> str:
    return uuid.uuid4().hex
