"""HTTP 服务测试（TestClient + 真库）：retrieve 出处字段 + 租户隔离。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from knowledge_rag.app import app

client = TestClient(app)


@pytest.fixture(scope="module")
def ids():
    import os

    import psycopg

    dsn = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("select id from tenants where code='shanqueli-demo'")
        tid = cur.fetchone()[0]
        cur.execute(
            "select v.id from venues v join tenants t on t.id=v.tenant_id "
            "where t.code='shanqueli-demo'"
        )
        vid = cur.fetchone()[0]
    return tid, vid


def test_retrieve_returns_provenance(ids):
    tid, vid = ids
    r = client.post(
        "/knowledge/retrieve",
        json={"tenant_id": tid, "venue_id": vid, "query": "商场几点关门", "threshold": 0.0},
    )
    body = r.json()
    assert r.status_code == 200 and 0 < len(body["items"]) <= 5
    for item in body["items"]:
        assert item["document_id"] > 0 and item["title"] and item["content"]


def test_retrieve_tenant_isolation(ids):
    _tid, vid = ids
    r = client.post(
        "/knowledge/retrieve",
        json={"tenant_id": 99999, "venue_id": vid, "query": "商场几点关门", "threshold": 0.0},
    )
    assert r.json()["items"] == [], "跨租户必须为空"
