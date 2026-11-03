"""入库管道集成测试（真实库 + MockProvider 确定性向量，无网络）。"""

from __future__ import annotations

import os

import psycopg
import pytest
from _pytest.monkeypatch import MonkeyPatch
from knowledge_rag.ingest import ingest_venue
from knowledge_rag.provider import MockProvider, ProviderConfig


@pytest.fixture(scope="module")
def provider():
    mp = MonkeyPatch()
    yield MockProvider(ProviderConfig.from_env())  # 默认 EMBED_DIM=1024，与列定义一致
    mp.undo()


def _dsn() -> str:
    return os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)


def _chunk_count() -> int:
    with psycopg.connect(_dsn()) as conn, conn.cursor() as cur:
        cur.execute("select count(*) from knowledge_chunks")
        return cur.fetchone()[0]


def test_ingest_idempotent_and_counts(provider):
    r1 = ingest_venue("山雀里·栖云广场", "shanqueli-demo", provider=provider, dsn=_dsn())
    n1 = _chunk_count()
    r2 = ingest_venue("山雀里·栖云广场", "shanqueli-demo", provider=provider, dsn=_dsn())
    n2 = _chunk_count()
    assert r1["documents"] == 100, "应处理全部 100 篇文档"
    assert r1["chunks"] == n1 and r2["chunks"] == n2, "幂等：重跑行数不变"
    assert n1 >= 100, "至少每文档 1 片"


def test_ingest_chunks_have_vectors_and_metadata(provider):
    ingest_venue("山雀里·栖云广场", "shanqueli-demo", provider=provider, dsn=_dsn())
    with psycopg.connect(_dsn()) as conn, conn.cursor() as cur:
        cur.execute(
            "select chunk_index, token_count, embedding is not null "
            "from knowledge_chunks order by document_id, chunk_index limit 5"
        )
        rows = cur.fetchall()
    for idx, tok, has_vec in rows:
        assert idx >= 0 and tok > 0 and has_vec
