"""knowledge-rag HTTP 服务（M0 契约形态）：POST /knowledge/retrieve。"""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from .retrieval import retrieve

app = FastAPI(title="knowledge-rag", version="0.1.0")


class RetrieveRequest(BaseModel):
    tenant_id: int
    venue_id: int
    query: str
    threshold: float | None = None


@app.get("/health")
def health() -> dict:
    return {"ok": True}


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
