"""knowledge-rag HTTP 服务（M0 契约形态）：POST /knowledge/retrieve、POST /knowledge/ingest。"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .ingest import UnknownDocuments, _dsn, ingest_documents
from .retrieval import retrieve

app = FastAPI(title="knowledge-rag", version="0.1.0")


class RetrieveRequest(BaseModel):
    tenant_id: int
    venue_id: int
    query: str
    threshold: float | None = None


class IngestRequest(BaseModel):
    tenant_id: int
    venue_id: int | None = None  # 全量（document_ids 缺省）时必填
    document_ids: list[int] | None = None


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/knowledge/ingest")
def knowledge_ingest(req: IngestRequest) -> dict:
    """重嵌知识文档（M6）：全量（缺省）或按 document_ids 增量；同步执行。

    业务错误（M0 风格）：HTTP 200 + error_code=4004（文档不存在/越权不可见）。
    """
    if req.document_ids is None:
        if req.venue_id is None:
            raise HTTPException(status_code=422, detail="venue_id 必填（全量重嵌）")
        return ingest_documents(None, dsn=_dsn(), tenant_id=req.tenant_id,
                                venue_id=req.venue_id)
    try:
        return ingest_documents(req.document_ids, dsn=_dsn(),
                                tenant_id=req.tenant_id)
    except UnknownDocuments as e:
        return {"error_code": 4004, "message": "知识文档不存在或不可见",
                "unknown": e.unknown}


@app.post("/knowledge/retrieve")
def knowledge_retrieve(req: RetrieveRequest) -> dict:
    items = retrieve(req.tenant_id, req.venue_id, req.query, threshold=req.threshold)
    return {
        "items": [
            {"document_id": r.document_id, "title": r.title, "content": r.content,
             "score": r.score, "rerank_score": r.rerank_score, "source": r.source}
            for r in items
        ]
    }
