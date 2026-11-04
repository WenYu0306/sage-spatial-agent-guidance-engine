"""M9 analytics 验收：批量埋点幂等、11 指标聚合、范围与角色控制（PRD 7.4/15）。"""

from __future__ import annotations

import datetime as dt

import pytest
from analytics_service.app import create_app
from fastapi.testclient import TestClient

METRICS = [
    "ai_query_count", "search_keyword_top", "poi_search_rank", "route_plan_count",
    "hot_destination_top", "poi_recommend_count", "coupon_claim_count",
    "coupon_use_count", "device_usage_count", "traffic_by_hour", "handover_rate",
]


@pytest.fixture(scope="module")
def client(dsn):
    return TestClient(create_app(dsn=dsn))


@pytest.fixture(scope="module")
def tokens(client, accounts):
    out = {}
    for username in ("rbac_admin", "rbac_merchant"):
        r = client.post("/api/v1/auth/login", json={
            "tenant_code": "shanqueli-demo", "username": username,
            "password": accounts["password"]})
        out[username] = r.json()["access_token"]
    return out


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def seeded_events(client, accounts, dsn):
    """灌 3 天窗口事件：3 次 ai_query、1 次 route_plan、2 次 coupon_claim。"""
    now = dt.datetime.now(dt.timezone.utc)
    events = []
    for i in range(3):
        events.append({
            "tenant_id": accounts["tid"], "venue_id": accounts["vid"],
            "event_id": f"m9-aiq-{i}", "event_type": "ai_query",
            "actor_type": "guest", "actor_id": f"anon-{i}",
            "occurred_at": now - dt.timedelta(days=i),
            "payload": {"intent": "poi_recommend", "latency_ms": 900 + i,
                        "degraded": False, "tool_count": 2},
        })
    events.append({
        "tenant_id": accounts["tid"], "venue_id": accounts["vid"],
        "event_id": "m9-route-1", "event_type": "route_plan", "actor_type": "guest",
        "occurred_at": now, "payload": {"distance_meter": 110},
    })
    events.append({
        "tenant_id": accounts["tid"], "venue_id": accounts["vid"],
        "event_id": "m9-coupon-1", "event_type": "coupon_claim", "actor_type": "guest",
        "subject_type": "coupon", "subject_id": 1, "occurred_at": now,
        "payload": {"coupon_id": 1, "poi_id": accounts["store_poi"]},
    })
    wire = [{**e, "occurred_at": e["occurred_at"].isoformat()} for e in events]
    r = client.post("/api/v1/events", json={"events": wire})
    assert r.status_code == 200, r.text
    return wire


def test_post_events_batch_idempotent(client, accounts, seeded_events):
    replay = client.post("/api/v1/events", json={"events": seeded_events[:3]})
    body = replay.json()
    assert replay.status_code == 200
    assert body["inserted"] == 0 and body["skipped"] == 3, "重放全跳过"


def test_post_events_rejects_over_50(client, accounts):
    events = [{"tenant_id": accounts["tid"], "venue_id": accounts["vid"],
               "event_id": f"over-{i}", "event_type": "search", "actor_type": "guest",
               "occurred_at": dt.datetime.now(dt.timezone.utc).isoformat()}
              for i in range(51)]
    r = client.post("/api/v1/events", json={"events": events})
    assert r.status_code == 422


def test_post_events_rejects_unknown_type(client, accounts):
    r = client.post("/api/v1/events", json={"events": [{
        "tenant_id": accounts["tid"], "venue_id": accounts["vid"],
        "event_id": "bad-type-1", "event_type": "mystery", "actor_type": "guest",
        "occurred_at": dt.datetime.now(dt.timezone.utc).isoformat()}]})
    assert r.status_code == 200 and r.json()["error_code"] == 1001, "字典外类型整批拒收"


def test_overview_metrics(client, tokens, seeded_events):
    r = client.get("/api/v1/metrics/overview", headers=_h(tokens["rbac_admin"]),
                   params={"date_from": dt.date.today().isoformat(),
                           "date_to": dt.date.today().isoformat()})
    body = r.json()
    assert r.status_code == 200
    assert body["metrics"]["ai_query_count"] >= 3
    assert body["metrics"]["route_plan_count"] >= 1
    assert body["metrics"]["coupon_claim_count"] >= 1


def test_metric_code_timeseries_day_and_hour(client, tokens, seeded_events):
    h = _h(tokens["rbac_admin"])
    for code in ("ai_query_count", "route_plan_count"):
        day = client.get(f"/api/v1/metrics/{code}", headers=h,
                         params={"granularity": "day"}).json()
        assert day["points"], f"{code} day 时序非空"
        assert all("date" in p and "value" in p for p in day["points"])
    hour = client.get("/api/v1/metrics/ai_query_count", headers=h,
                      params={"granularity": "hour"}).json()
    assert hour["points"]


def test_all_eleven_metric_codes_registered(client, tokens):
    r = client.get("/api/v1/metrics/codes", headers=_h(tokens["rbac_admin"]))
    assert set(r.json()["codes"]) == set(METRICS)


def test_merchant_scope_on_own_store_only(client, tokens, accounts):
    r = client.get(f"/api/v1/metrics/merchant/{accounts['store_poi']}",
                   headers=_h(tokens["rbac_merchant"]))
    assert r.status_code == 200
    other = client.get(f"/api/v1/metrics/merchant/{accounts['store_poi'] + 1}",
                       headers=_h(tokens["rbac_merchant"]))
    assert other.status_code == 403 and other.json()["error_code"] == 1003


def test_unauthenticated_401(client):
    assert client.get("/api/v1/metrics/overview").status_code == 401
