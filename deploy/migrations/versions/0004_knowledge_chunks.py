"""0004：知识切片表 + pgvector 扩展（PRD 6.5 DDL 落地，供 M6 RAG 管道）。

knowledge_chunks：embedding 维度 vector(1024)——按当前选定的 embedding 模型
维度冻结，若最终模型不同以新迁移调整；ivfflat 余弦索引随表建立。

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-04
"""

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

UPGRADE_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE knowledge_chunks (
  id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  document_id BIGINT NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
  tenant_id  BIGINT NOT NULL,
  venue_id   BIGINT NOT NULL,
  chunk_index INT NOT NULL,
  content    TEXT NOT NULL,
  token_count INT NOT NULL,
  embedding  vector(1024),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (document_id, chunk_index)
);
CREATE INDEX idx_chunks_embedding ON knowledge_chunks USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX idx_chunks_venue ON knowledge_chunks(tenant_id, venue_id);
"""


def upgrade() -> None:
    from alembic import op

    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    from alembic import op

    op.execute("DROP TABLE IF EXISTS knowledge_chunks;")
