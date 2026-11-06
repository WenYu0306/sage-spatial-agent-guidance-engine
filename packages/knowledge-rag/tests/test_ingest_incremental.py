"""增量入库（M6 TDD）：指定文档重嵌不伤邻居、缩文清尾、端点契约与 4004。

真实库 + MockProvider 确定性向量（沿 test_ingest.py 模式，无网络）。
"""

from __future__ import annotations

import os
import uuid

import psycopg
import pytest
from _pytest.monkeypatch import MonkeyPatch
from fastapi.testclient import TestClient
from knowledge_rag.ingest import UnknownDocuments, ingest_venue
from platform_core.llm import MockProvider, ProviderConfig


@pytest.fixture(scope="module")
def provider():
    mp = MonkeyPatch()
    yield MockProvider(ProviderConfig.from_env())
    mp.undo()
    from platform_core.llm import make_provider

    ingest_venue("山雀里·栖云广场", "shanqueli-demo", provider=make_provider())


def _dsn() -> str:
    return os.environ["DATABASE_URL"].replace(
        "postgresql+psycopg://", "postgresql://", 1)


def _mk_doc(cur, title: str, content: str) -> int:
    cur.execute(
        "select v.tenant_id, v.id from venues v join tenants t on t.id=v.tenant_id "
        "where t.code='shanqueli-demo' and v.name='山雀里·栖云广场'")
    tid, vid = cur.fetchone()
    cur.execute(
        "insert into knowledge_documents (tenant_id, venue_id, doc_type, title, "
        "content, status) values (%s, %s, 'faq', %s, %s, 'active') returning id",
        (tid, vid, title, content))
    return cur.fetchone()[0]


def _rm_doc(conn, doc_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute("delete from knowledge_chunks where document_id=%s", (doc_id,))
        cur.execute("delete from knowledge_documents where id=%s", (doc_id,))
    conn.commit()


def _doc_chunks(cur, doc_id: int) -> list:
    cur.execute("select chunk_index, content from knowledge_chunks "
                "where document_id=%s order by chunk_index", (doc_id,))
    return cur.fetchall()


def test_incremental_leaves_neighbor_untouched(provider):
    from knowledge_rag.ingest import ingest_documents

    marker = uuid.uuid4().hex[:8]
    dsn = _dsn()
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        a = _mk_doc(cur, f"增量A{marker}", "火锅店的营业时间是从上午十点到晚上十点。" * 30)
        b = _mk_doc(cur, f"增量B{marker}", "会员积分每逢周末双倍累计。" * 30)
    try:
        ingest_documents([a, b], provider=provider, dsn=dsn)  # 基线
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            baseline_b = _doc_chunks(cur, b)

        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute("update knowledge_documents set content=%s where id=%s",
                        ("改版后的内容，停车场夜间免费。" * 40, a))
        stat = ingest_documents([a], provider=provider, dsn=dsn)

        assert stat["documents"] == 1, "增量只处理指定文档"
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            assert _doc_chunks(cur, b) == baseline_b, "邻居文档 chunk 不得被触碰"
    finally:
        with psycopg.connect(dsn) as conn:
            _rm_doc(conn, a)
            _rm_doc(conn, b)


def test_shrunk_doc_clears_stale_tail(provider):
    from knowledge_rag.ingest import ingest_documents

    marker = uuid.uuid4().hex[:8]
    dsn = _dsn()
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        d = _mk_doc(cur, f"缩文{marker}", "长文档第一段。" * 400)
    try:
        ingest_documents([d], provider=provider, dsn=dsn)
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            before = len(_doc_chunks(cur, d))
        assert before >= 2

        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute("update knowledge_documents set content=%s where id=%s",
                        ("只剩一句。", d))
        stat = ingest_documents([d], provider=provider, dsn=dsn)

        assert stat["deleted"] == before, "旧块全部清除（gross 口径：先删后插）"
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            after = _doc_chunks(cur, d)
        assert len(after) == 1 and after[0][1] == "只剩一句。"
    finally:
        with psycopg.connect(dsn) as conn:
            _rm_doc(conn, d)


def test_unknown_doc_id_raises(provider):
    from knowledge_rag.ingest import ingest_documents

    with pytest.raises(UnknownDocuments) as ei:
        ingest_documents([999999999], provider=provider, dsn=_dsn())
    assert 999999999 in ei.value.unknown


def test_endpoint_contract(provider, monkeypatch):
    """端点三形态：全量（None=缺省）、增量、4004（core 打桩不真嵌）。"""
    import knowledge_rag.app as kapp

    calls: list = []

    def fake_core(doc_ids, provider=None, dsn=None, tenant_id=None, venue_id=None):
        calls.append(doc_ids)
        if doc_ids == [777]:
            raise UnknownDocuments([777])
        return {"documents": len(doc_ids or []), "chunks": 3, "deleted": 0}

    monkeypatch.setattr(kapp, "ingest_documents", fake_core)
    client = TestClient(kapp.app)

    r = client.post("/knowledge/ingest", json={"tenant_id": 1, "venue_id": 1})
    assert r.status_code == 200 and r.json()["chunks"] == 3
    assert calls[-1] is None, "缺省 document_ids 应传 None（全量语义）"

    r = client.post("/knowledge/ingest",
                    json={"tenant_id": 1, "venue_id": 1, "document_ids": [5, 9]})
    assert r.json()["documents"] == 2 and calls[-1] == [5, 9]

    r = client.post("/knowledge/ingest",
                    json={"tenant_id": 1, "venue_id": 1, "document_ids": [777]})
    assert r.json()["error_code"] == 4004
    assert 777 in r.json()["unknown"]
