"""0008：埋点与指标表（PRD 6.5/15 节 DDL 落地，M9 analytics 数据层）。

events：客户端生成 event_id 幂等去重；metrics_daily：预聚合目标表，
demo 读路径即时聚合（D-025），本表留 V2 定时聚合写入口。

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-04
"""

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

UPGRADE_SQL = """
CREATE TABLE events (
  id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id    BIGINT NOT NULL,
  venue_id     BIGINT NOT NULL,
  event_id     VARCHAR(64) NOT NULL UNIQUE,    -- 客户端生成，幂等去重
  event_type   VARCHAR(48) NOT NULL,           -- 见 PRD 15 节事件字典
  subject_type VARCHAR(32) NULL,               -- poi/coupon/device/route/query
  subject_id   BIGINT NULL,
  actor_type   VARCHAR(16) NOT NULL,           -- guest/merchant/venue_admin/device
  actor_id     VARCHAR(64) NULL,
  device_id    BIGINT NULL,
  floor_id     BIGINT NULL,
  session_id   BIGINT NULL,
  payload      JSONB NOT NULL DEFAULT '{}',
  trace_id     VARCHAR(64) NULL,
  occurred_at  TIMESTAMPTZ NOT NULL,
  received_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_events_venue_time ON events(venue_id, occurred_at);
CREATE INDEX idx_events_type_time  ON events(event_type, occurred_at);

CREATE TABLE metrics_daily (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id   BIGINT NOT NULL,
  venue_id    BIGINT NOT NULL,
  metric_date DATE NOT NULL,
  metric_code VARCHAR(48) NOT NULL,            -- ai_query_count/search_keyword_top/...
  dim_type    VARCHAR(32) NOT NULL DEFAULT 'venue', -- venue/floor/device/poi/hour
  dim_value   VARCHAR(64) NOT NULL DEFAULT 'all',
  value       NUMERIC(16,2) NOT NULL,
  UNIQUE (venue_id, metric_date, metric_code, dim_type, dim_value)
);
"""


def upgrade() -> None:
    from alembic import op

    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    from alembic import op

    op.execute("DROP TABLE IF EXISTS metrics_daily; DROP TABLE IF EXISTS events;")
