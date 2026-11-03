"""检索服务测试：租户隔离、阈值空结果、Top5 上限、关键词降级（真库 + mock 向量）。"""

from __future__ import annotations

import os

import pytest
from knowledge_rag.retrieval import retrieve
from platform_core.llm import MockProvider, ProviderConfig, ProviderUnavailableError

TENANT_SQL = "select id from tenants where code='shanqueli-demo'"
VENUE_SQL = (
    "select v.id from venues v join tenants t on t.id=v.tenant_id "
    "where t.code='shanqueli-demo'"
)


@pytest.fixture(scope="module")
def ids():
    with psycopg_connect() as conn, conn.cursor() as cur:
        cur.execute(TENANT_SQL)
        tid = cur.fetchone()[0]
        cur.execute(VENUE_SQL)
        vid = cur.fetchone()[0]
    return tid, vid


def psycopg_connect():
    import psycopg

    return psycopg.connect(
        os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
    )


@pytest.fixture(scope="module")
def provider():
    return MockProvider(ProviderConfig.from_env())


def test_vector_retrieve_returns_provenance(ids, provider):
    tid, vid = ids
    results = retrieve(tid, vid, "商场几点关门", provider=provider, threshold=0.0)
    assert 0 < len(results) <= 5
    for r in results:
        assert r.document_id > 0 and r.title and r.content
        assert r.source == "vector"


def test_threshold_drops_all_when_sim_low(ids, provider):
    tid, vid = ids
    results = retrieve(tid, vid, "商场几点关门", provider=provider, threshold=0.99)
    assert results == [], "阈值之上无结果必须明确返回空（禁止硬凑）"


def test_tenant_isolation(ids, provider):
    _tid, vid = ids
    results = retrieve(99999, vid, "商场几点关门", provider=provider, threshold=0.0)
    assert results == [], "跨租户必须查不到任何片段"


def test_keyword_fallback_when_provider_down(ids):
    tid, vid = ids

    class Dead:
        def embed(self, texts):
            raise ProviderUnavailableError("模拟不可用")

    results = retrieve(tid, vid, "停车场怎么收费", provider=Dead(), threshold=0.0)
    assert len(results) >= 1, "降级关键词检索应有结果"
    assert all(r.source == "keyword" for r in results)
    assert any("停车" in r.title or "停车" in r.content for r in results)
