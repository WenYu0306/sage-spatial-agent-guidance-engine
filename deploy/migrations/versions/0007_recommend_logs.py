"""0007：推荐日志表（PRD 6.5 DDL 落地，M7 打分明细留痕）。

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-04
"""

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

UPGRADE_SQL = """
CREATE TABLE recommend_logs (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id   BIGINT NOT NULL,
  venue_id    BIGINT NOT NULL,
  message_id  BIGINT NULL,
  poi_id      BIGINT NOT NULL,
  score       NUMERIC(10,4) NOT NULL,
  factors     JSONB NOT NULL,                  -- 各因子得分明细
  reasons     JSONB NOT NULL,                  -- 展示用理由
  rank        INT NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_ranklogs_msg ON recommend_logs(message_id);
"""


def upgrade() -> None:
    from alembic import op

    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    from alembic import op

    op.execute("DROP TABLE IF EXISTS recommend_logs;")
