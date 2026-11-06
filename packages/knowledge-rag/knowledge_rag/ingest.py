"""知识入库管道：读 knowledge_documents → 切片 → 向量化 → 幂等 upsert chunks。

幂等定义：同内容重跑行数不变（按 document_id+chunk_index upsert）。
embedding 用 psycopg 文本字面量写入（'[v1,v2,...]'::vector）。
"""

from __future__ import annotations

import os

import psycopg
from platform_core.llm import make_provider

from .chunking import estimate_tokens, split_into_chunks


def _dsn() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise SystemExit("DATABASE_URL 未设置：复制 .env.example 为 .env")
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


class UnknownDocuments(ValueError):
    """指定文档不存在（或越权不可见）：携带 unknown id 列表（M6 → 4004）。"""

    def __init__(self, unknown: list[int]):
        super().__init__(f"unknown document ids: {unknown}")
        self.unknown = unknown


def _write_chunks(cur, pieces: list[tuple[int, int, str]], provider) -> int:
    """分批 embedding（供应商上限对齐）+ upsert；由调用方掌管事务。"""
    BATCH = provider.config.embed_batch_size  # 供应商上限（百炼=10）
    written = 0
    for start in range(0, len(pieces), BATCH):
        batch = pieces[start:start + BATCH]
        vecs = provider.embed([p[2] for p in batch])
        for (doc_id, i, piece), vec in zip(batch, vecs):
            cur.execute(
                "insert into knowledge_chunks (document_id, tenant_id, venue_id, "
                "chunk_index, content, token_count, embedding) "
                "select %s, d.tenant_id, d.venue_id, %s, %s, %s, %s::vector "
                "from knowledge_documents d where d.id = %s "
                "on conflict (document_id, chunk_index) do update set "
                "content=excluded.content, token_count=excluded.token_count, "
                "embedding=excluded.embedding",
                (doc_id, i, piece, estimate_tokens(piece), _vec_literal(vec), doc_id),
            )
            written += 1
    return written


def ingest_documents(
    doc_ids: list[int] | None,
    provider=None,
    dsn: str | None = None,
    tenant_id: int | None = None,
    venue_id: int | None = None,
) -> dict:
    """重嵌知识文档（M6）：doc_ids=None 时按 tenant+venue 解析全部 active（全量）。

    给定 doc_ids 为增量（先删后插，单事务：嵌入失败整体回滚，检索无空窗）；
    tenant_id 给定时做归属校验（跨租户 id 视为不存在 → UnknownDocuments/4004）。
    """
    provider = provider or make_provider()
    dsn = dsn or _dsn()
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        if doc_ids is None:
            cur.execute(
                "select id from knowledge_documents where tenant_id=%s and "
                "venue_id=%s and status='active' order by id",
                (tenant_id, venue_id))
            doc_ids = [r[0] for r in cur.fetchall()]
        else:
            q = "select id from knowledge_documents where id = any(%s)"
            args: tuple = (list(doc_ids),)
            if tenant_id is not None:  # 归属校验：跨租户 id 视为不存在
                q += " and tenant_id = %s"
                args = (list(doc_ids), tenant_id)
            cur.execute(q, args)
            found = {r[0] for r in cur.fetchall()}
            unknown = [d for d in doc_ids if d not in found]
            if unknown:
                raise UnknownDocuments(unknown)

        deleted = 0
        all_pieces: list[tuple[int, int, str]] = []
        for doc_id in doc_ids:
            cur.execute("delete from knowledge_chunks where document_id=%s", (doc_id,))
            deleted += cur.rowcount
            cur.execute("select content from knowledge_documents where id=%s", (doc_id,))
            content = cur.fetchone()[0]
            for i, piece in enumerate(split_into_chunks(content)):
                all_pieces.append((doc_id, i, piece))
        written = _write_chunks(cur, all_pieces, provider)
    return {"documents": len(doc_ids), "chunks": written, "deleted": deleted}


def ingest_venue(venue_name: str, tenant_code: str, provider=None, dsn: str | None = None) -> dict:
    """对单个场馆的全部 active 文档做切片+向量化入库。返回统计。"""
    provider = provider or make_provider()
    dsn = dsn or _dsn()
    docs = chunks_written = 0
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "select d.id, d.content from knowledge_documents d "
            "join tenants t on t.id = d.tenant_id "
            "where t.code = %s and d.venue_id = ("
            "  select id from venues where tenant_id = t.id and name = %s) "
            "and d.status = 'active' order by d.id",
            (tenant_code, venue_name),
        )
        rows = cur.fetchall()

        # 先全部切片，再分批 embedding（每批一次 API 调用，省额且对齐每日上限语义）
        pieces: list[tuple[int, int, str]] = []
        for doc_id, content in rows:
            docs += 1
            for i, piece in enumerate(split_into_chunks(content)):
                pieces.append((doc_id, i, piece))

        BATCH = provider.config.embed_batch_size  # 供应商上限（百炼=10）
        for start in range(0, len(pieces), BATCH):
            batch = pieces[start:start + BATCH]
            vecs = provider.embed([p[2] for p in batch])
            for (doc_id, i, piece), vec in zip(batch, vecs):
                cur.execute(
                    "insert into knowledge_chunks (document_id, tenant_id, venue_id, "
                    "chunk_index, content, token_count, embedding) "
                    "select %s, d.tenant_id, d.venue_id, %s, %s, %s, %s::vector "
                    "from knowledge_documents d where d.id = %s "
                    "on conflict (document_id, chunk_index) do update set "
                    "content=excluded.content, token_count=excluded.token_count, "
                    "embedding=excluded.embedding",
                    (doc_id, i, piece, estimate_tokens(piece), _vec_literal(vec), doc_id),
                )
                chunks_written += 1
    return {"documents": docs, "chunks": chunks_written}


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="知识切片+向量化入库（幂等）")
    ap.add_argument("--venue", default="山雀里·栖云广场")
    ap.add_argument("--tenant", default="shanqueli-demo")
    args = ap.parse_args()
    print(ingest_venue(args.venue, args.tenant))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
