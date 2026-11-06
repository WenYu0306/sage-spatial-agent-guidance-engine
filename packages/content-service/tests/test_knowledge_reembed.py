"""M6 触发链路：知识文档 POST/PATCH → knowledge-rag 增量重嵌（mock transport）。

覆盖：触发携带 document_ids；触发失败不阻断编辑（文档已保存）。
"""

from __future__ import annotations

import json
import uuid

import httpx
import os
import psycopg
import pytest


class _Recorder(httpx.BaseTransport):
    """记录 /knowledge/ingest 请求；fail=True 时模拟连接失败。"""

    calls: list[dict] = []
    fail = False

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if self.fail:
            raise httpx.ConnectError("boom", request=request)
        _Recorder.calls.append(json.loads(request.content.decode()))
        return httpx.Response(200, json={"documents": 1, "chunks": 2, "deleted": 0})


@pytest.fixture()
def _cleanup_docs():
    """测试建的文档（含 chunks）用后即清——否则污染 seed 行数断言（教训重演）。"""
    yield
    dsn = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("delete from knowledge_chunks where document_id in "
                    "(select id from knowledge_documents "
                    "where title like '重嵌%' or title like '改题%')")
        cur.execute("delete from knowledge_documents "
                    "where title like '重嵌%' or title like '改题%'")
        conn.commit()


@pytest.fixture()
def rec(client):
    r = _Recorder()
    client.app.state.http_knowledge = httpx.Client(transport=r, base_url="http://k")
    _Recorder.calls.clear()
    _Recorder.fail = False
    return r


def _mk_doc(client, token, marker):
    resp = client.post(
        "/api/v1/knowledge-documents",
        headers={"Authorization": f"Bearer {token}"},
        json={"venue_id": 1, "doc_type": "faq", "title": f"重嵌{marker}",
              "content": "测试内容：" + "细节。" * 50})
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def test_patch_triggers_reembed_with_doc_id(client, tokens, rec, _cleanup_docs):
    marker = uuid.uuid4().hex[:8]
    did = _mk_doc(client, tokens["rbac_editor"], marker)
    assert rec.calls and rec.calls[-1]["document_ids"] == [did], "创建即触发重嵌"

    resp = client.patch(f"/api/v1/knowledge-documents/{did}",
                        headers={"Authorization": f"Bearer {tokens['rbac_editor']}"},
                        json={"content": "改版内容：" + "新细节。" * 50})
    assert resp.status_code == 200
    assert rec.calls[-1]["document_ids"] == [did], "PATCH 触发增量重嵌"
    assert resp.json()["version"] == 2


def test_reembed_failure_does_not_block_edit(client, tokens, rec, _cleanup_docs):
    marker = uuid.uuid4().hex[:8]
    did = _mk_doc(client, tokens["rbac_editor"], marker)
    rec.fail = True
    resp = client.patch(f"/api/v1/knowledge-documents/{did}",
                        headers={"Authorization": f"Bearer {tokens['rbac_editor']}"},
                        json={"title": f"改题{marker}"})
    assert resp.status_code == 200, "触发失败不得阻断编辑"
    assert resp.json()["version"] == 2
