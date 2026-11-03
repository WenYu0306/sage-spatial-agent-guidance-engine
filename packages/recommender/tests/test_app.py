"""M7 服务层验收：特征装配（真实 DB 泛化列）、范围过滤、recommend_logs 落库。

需要 DATABASE_URL 与已灌 seed（make migrate && make seed）。
"""

from __future__ import annotations

import json

import psycopg
import pytest
from fastapi.testclient import TestClient
from recommender.app import create_app


@pytest.fixture(scope="module")
def ctx_ids(dsn):
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("select id from tenants where code='shanqueli-demo'")
        tid = cur.fetchone()[0]
        cur.execute("select id from venues where tenant_id=%s limit 1", (tid,))
        vid = cur.fetchone()[0]
        cur.execute(
            "select p.id, p.floor_id from pois p join poi_categories c "
            "on c.tenant_id=p.tenant_id and c.code=p.category_code "
            "where p.tenant_id=%s and p.deleted_at is null "
            "and c.is_facility=false and p.floor_id = "
            "(select id from floors where venue_id=%s and level=1) "
            "order by p.id limit 3", (tid, vid))
        rows = cur.fetchall()
        cur.execute("select id from floors where venue_id=%s and level=1", (vid,))
        f1 = cur.fetchone()[0]
    return {"tid": tid, "vid": vid, "pois": rows, "f1": f1}


@pytest.fixture(scope="module")
def client(dsn, monkeypatch_module):
    return TestClient(create_app(dsn=dsn))


@pytest.fixture(scope="module")
def monkeypatch_module():
    """营业状态时间注入：统一取 12:00（seed 时段 10:00-22:00 内，全部营业中）。"""
    import os

    os.environ["SAGE_TIME_OVERRIDE"] = "2026-11-04T12:00:00"
    yield
    os.environ.pop("SAGE_TIME_OVERRIDE", None)


def _rank(client, ids, ctx_ids, **kw):
    body = {"tenant_id": ctx_ids["tid"], "venue_id": ctx_ids["vid"],
            "candidates": ids, "position": {"x": 600.0, "y": 400.0,
                                            "floor_id": ctx_ids["f1"]},
            "tags": kw.pop("tags", []), **kw}
    return client.post("/recommend/rank", json=body)


def test_rank_orders_desc_with_full_factors(client, ctx_ids):
    ids = [r[0] for r in ctx_ids["pois"]]
    r = _rank(client, ids, ctx_ids, tags=["约会"])
    assert r.status_code == 200
    ranked = r.json()["ranked"]
    assert len(ranked) == 3
    scores = [row["score"] for row in ranked]
    assert scores == sorted(scores, reverse=True)
    for row in ranked:
        assert len(row["factors"]) == 8 and 0.0 <= row["score"] <= 1.0
        assert 1 <= len(row["reasons"]) <= 3


def test_promotion_flag_scores_full(client, ctx_ids):
    ids = [r[0] for r in ctx_ids["pois"]]
    promo_id = ids[0]
    ranked = _rank(client, ids, ctx_ids, promotion_poi_ids=[promo_id]).json()["ranked"]
    by_id = {row["poi_id"]: row for row in ranked}
    assert by_id[promo_id]["factors"]["promotion"] == pytest.approx(1.0)
    assert by_id[ids[1]]["factors"]["promotion"] == pytest.approx(0.0)


def test_writes_recommend_logs(client, ctx_ids, dsn):
    import time

    msg_id = int(time.time() * 1000) % 10**9  # 日志表累加，用唯一 id 圈定本次
    ids = [r[0] for r in ctx_ids["pois"]]
    _rank(client, ids, ctx_ids, message_id=msg_id)
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "select poi_id, rank, factors, reasons from recommend_logs "
            "where message_id=%s order by rank", (msg_id,))
        rows = cur.fetchall()
    assert len(rows) == 3 and [r[1] for r in rows] == [1, 2, 3]
    assert set(rows[0][2]) >= {"distance", "hot"}  # psycopg 已反序列化 JSONB


def test_foreign_tenant_and_unknown_ids_ignored(client, ctx_ids):
    r = _rank(client, [999999001, 999999002], ctx_ids)
    assert r.json()["ranked"] == []


def test_empty_candidates_empty_result(client, ctx_ids):
    r = _rank(client, [], ctx_ids)
    assert r.status_code == 200 and r.json()["ranked"] == []


def test_closed_candidate_excluded(client, ctx_ids, dsn):
    """营业状态为闭店时段的候选被直接过滤（改 hours→调→还原）。"""
    pid = ctx_ids["pois"][0][0]
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("select business_hours from pois where id=%s", (pid,))
        original = cur.fetchone()[0]
        cur.execute(
            "update pois set business_hours=%s where id=%s",
            (json.dumps({d: ["03:00-04:00"] for d in
                         ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}),
             pid))
        conn.commit()
    try:
        ids = [r[0] for r in ctx_ids["pois"]]
        ranked = _rank(client, ids, ctx_ids).json()["ranked"]
        assert pid not in {row["poi_id"] for row in ranked}
        assert len(ranked) == 2
    finally:
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute("update pois set business_hours=%s where id=%s",
                        (json.dumps(original), pid))
            conn.commit()


def test_weights_readonly_endpoint(client):
    r = client.get("/recommend/weights").json()
    assert abs(sum(r["factors"].values()) - 1.0) < 1e-9
    assert r["editable"] is False and r["factors"]["distance"] == 0.22


def test_health(client):
    assert client.get("/health").json() == {"ok": True}
