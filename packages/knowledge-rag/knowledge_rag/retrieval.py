"""检索服务：租户强制过滤 + 向量 Top20 → 重排 Top5 → 阈值过滤 → 带出处。

- SQL 恒带 tenant_id 与 venue_id（越权防线，PRD 6.5 纪律）
- 相似度 = 1 - 余弦距离（pgvector <=>）；低于阈值（RAG_THRESHOLD，默认 0.35）丢弃，
  无结果明确返回空列表，禁止硬凑
- 重排：向量相似度 + 标题重合加分（可讲、无第二模型）
- Provider 不可用/超限 → 关键词降级（ILIKE 标题/正文，仍带出处与租户过滤）
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from platform_core.llm import DailyLimitError, ProviderUnavailableError, make_provider

TOP_K = 20
FINAL_K = 5


@dataclass(frozen=True)
class RetrievedChunk:
    document_id: int
    title: str
    content: str
    score: float
    rerank_score: float
    source: str  # vector / keyword


def _dsn() -> str:

    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise SystemExit("DATABASE_URL 未设置")
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def _cjk_bigrams(text: str) -> set[str]:
    cleaned = "".join(ch for ch in text if "一" <= ch <= "鿿")
    return {cleaned[i : i + 2] for i in range(len(cleaned) - 1)}


def retrieve(
    tenant_id: int,
    venue_id: int,
    query: str,
    provider=None,
    dsn: str | None = None,
    threshold: float | None = None,
) -> list[RetrievedChunk]:
    provider = provider or make_provider()
    dsn = dsn or _dsn()
    threshold = float(os.environ.get("RAG_THRESHOLD", "0.35")) if threshold is None else threshold
    try:
        return _vector_path(tenant_id, venue_id, query, provider, dsn, threshold)
    except (ProviderUnavailableError, DailyLimitError):
        return _keyword_path(tenant_id, venue_id, query, dsn)


def _vector_path(tenant_id, venue_id, query, provider, dsn, threshold) -> list[RetrievedChunk]:
    import psycopg

    qvec = provider.embed([query])[0]
    literal = "[" + ",".join(f"{x:.6f}" for x in qvec) + "]"
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "select c.document_id, d.title, c.content, "
            "1 - (c.embedding <=> %s::vector) as sim "
            "from knowledge_chunks c "
            "join knowledge_documents d on d.id = c.document_id "
            "where c.tenant_id = %s and c.venue_id = %s "
            "order by c.embedding <=> %s::vector limit %s",
            (literal, tenant_id, venue_id, literal, TOP_K),
        )
        rows = cur.fetchall()
    if not rows:
        return []
    q_terms = _cjk_bigrams(query)
    scored = []
    for doc_id, title, content, sim in rows:
        boost = 0.05 * len(q_terms & _cjk_bigrams(title))
        scored.append(
            RetrievedChunk(doc_id, title, content, float(sim), float(sim) + boost, "vector")
        )
    scored.sort(key=lambda r: r.rerank_score, reverse=True)
    kept = [r for r in scored if r.score >= threshold]
    return kept[:FINAL_K]


def _keyword_path(tenant_id, venue_id, query, dsn) -> list[RetrievedChunk]:
    import psycopg

    # 简单可讲的降级：取前 3 个二元组做 ILIKE
    terms = list(_cjk_bigrams(query))
    pats = [f"%{t}%" for t in terms[:3]]
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        if not pats:
            return []
        conds = []
        params: list = []
        for pat in pats:
            conds.append("(d.title ilike %s or c.content ilike %s)")
            params.extend([pat, pat])
        params.extend([tenant_id, venue_id])
        cur.execute(
            "select distinct c.document_id, d.title, c.content "
            "from knowledge_chunks c join knowledge_documents d on d.id = c.document_id "
            f"where ({' or '.join(conds)}) and c.tenant_id = %s and c.venue_id = %s "
            "limit %s",
            (*params, FINAL_K),
        )
        rows = cur.fetchall()
    return [RetrievedChunk(d, t, c, 0.0, 0.0, "keyword") for d, t, c in rows]
