"""M1 埋点 SDK 验收：track 单发/批量、event_id 幂等、事件字典校验（PRD 15）。"""

from __future__ import annotations

import datetime as dt

import psycopg
import pytest
from platform_core.events import EVENT_TYPES, track, track_batch


@pytest.fixture()
def ctx_ids(dsn):
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("select id from tenants where code='shanqueli-demo'")
        tid = cur.fetchone()[0]
        cur.execute("select id from venues where tenant_id=%s limit 1", (tid,))
        vid = cur.fetchone()[0]
    yield tid, vid
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("delete from events where event_id like 'sdk-test-%'")
        conn.commit()


def test_event_types_registry_matches_prd():
    assert set(EVENT_TYPES) >= {
        "ai_query", "ai_query_failed", "search", "poi_view", "poi_recommended",
        "route_plan", "route_handover", "coupon_claim", "coupon_use",
        "device_active", "ad_impression", "ad_click",
    }, "PRD 15 节事件字典 11+1 类"


def test_track_writes_event(dsn, ctx_ids):
    tid, vid = ctx_ids
    row = track(dsn, {
        "tenant_id": tid, "venue_id": vid, "event_id": "sdk-test-1",
        "event_type": "ai_query", "actor_type": "guest", "actor_id": "anon-1",
        "occurred_at": dt.datetime.now(dt.timezone.utc),
        "payload": {"intent": "poi_recommend", "latency_ms": 1234},
        "trace_id": "tr_sdk_1", "session_id": None,
    })
    assert row["id"] > 0 and row["duplicate"] is False
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("select payload from events where event_id='sdk-test-1'")
        assert cur.fetchone()[0]["intent"] == "poi_recommend"


def test_track_idempotent_on_duplicate_event_id(dsn, ctx_ids):
    tid, vid = ctx_ids
    base = {"tenant_id": tid, "venue_id": vid, "event_type": "search",
            "actor_type": "guest", "occurred_at": dt.datetime.now(dt.timezone.utc)}
    first = track(dsn, {**base, "event_id": "sdk-test-dup"})
    second = track(dsn, {**base, "event_id": "sdk-test-dup",
                         "payload": {"keyword": "different"}})
    assert first["duplicate"] is False and second["duplicate"] is True
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("select count(*) from events where event_id='sdk-test-dup'")
        assert cur.fetchone()[0] == 1, "重复 event_id 不得重复计数"


def test_track_rejects_unknown_event_type(dsn, ctx_ids):
    tid, vid = ctx_ids
    with pytest.raises(ValueError):
        track(dsn, {"tenant_id": tid, "venue_id": vid, "event_id": "sdk-test-bad",
                    "event_type": "not_in_dict", "actor_type": "guest",
                    "occurred_at": dt.datetime.now(dt.timezone.utc)})


def test_track_batch_skips_duplicates(dsn, ctx_ids):
    tid, vid = ctx_ids
    now = dt.datetime.now(dt.timezone.utc)
    result = track_batch(dsn, [
        {"tenant_id": tid, "venue_id": vid, "event_id": "sdk-test-b1",
         "event_type": "poi_view", "actor_type": "guest",
         "subject_type": "poi", "subject_id": 1, "occurred_at": now},
        {"tenant_id": tid, "venue_id": vid, "event_id": "sdk-test-b1",
         "event_type": "poi_view", "actor_type": "guest",
         "subject_type": "poi", "subject_id": 1, "occurred_at": now},
    ])
    assert result["inserted"] == 1 and result["skipped"] == 1
