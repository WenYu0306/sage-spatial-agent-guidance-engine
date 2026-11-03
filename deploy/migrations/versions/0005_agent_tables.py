"""0005：Agent 会话/消息/trace/工具注册表 + 券领取（PRD 6.4/6.5 DDL 落地，供 M5）。

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-04
"""

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

UPGRADE_SQL = """
-- ===== M5：Agent 会话与 trace =====
CREATE TABLE agent_tools (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  code        VARCHAR(64) NOT NULL UNIQUE,
  name        VARCHAR(128) NOT NULL,
  description TEXT NOT NULL,
  input_schema  JSONB NOT NULL,
  output_schema JSONB NOT NULL,
  endpoint    VARCHAR(255) NOT NULL,
  timeout_ms  INT NOT NULL DEFAULT 3000,
  enabled     BOOLEAN NOT NULL DEFAULT true,
  version     INT NOT NULL DEFAULT 1
);

CREATE TABLE agent_sessions (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id   BIGINT NOT NULL,
  venue_id    BIGINT NOT NULL,
  device_id   BIGINT NULL,
  anonymous_id VARCHAR(64) NULL,
  channel     VARCHAR(16) NOT NULL DEFAULT 'screen',
  status      VARCHAR(16) NOT NULL DEFAULT 'active',
  handed_to_session_id BIGINT NULL,
  started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_active_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE agent_messages (
  id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  session_id BIGINT NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
  tenant_id  BIGINT NOT NULL,
  role       VARCHAR(16) NOT NULL,
  content    TEXT NOT NULL,
  structured JSONB NULL,
  tokens_in  INT NULL,
  tokens_out INT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE agent_traces (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  session_id  BIGINT NOT NULL,
  message_id  BIGINT NOT NULL,
  tenant_id   BIGINT NOT NULL,
  trace_id    VARCHAR(64) NOT NULL,
  step_index  INT NOT NULL,
  step_type   VARCHAR(32) NOT NULL,
  tool_code   VARCHAR(64) NULL,
  input       JSONB NULL,
  output      JSONB NULL,
  status      VARCHAR(16) NOT NULL,
  latency_ms  INT NOT NULL,
  error_code  INT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_trace_msg ON agent_traces(message_id, step_index);
CREATE INDEX idx_trace_tid ON agent_traces(trace_id);

-- ===== M8 前置：券领取（幂等键唯一） =====
CREATE TABLE coupon_claims (
  id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id     BIGINT NOT NULL REFERENCES tenants(id),
  coupon_id     BIGINT NOT NULL REFERENCES coupons(id) ON DELETE CASCADE,
  anonymous_id  VARCHAR(64) NOT NULL,
  claim_status  VARCHAR(16) NOT NULL DEFAULT 'claimed',
  claimed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  used_at       TIMESTAMPTZ NULL,
  idempotency_key VARCHAR(128) NOT NULL UNIQUE
);
CREATE INDEX idx_claims_coupon ON coupon_claims(coupon_id);
"""


def upgrade() -> None:
    from alembic import op

    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    from alembic import op

    op.execute(
        """
        DROP TABLE IF EXISTS coupon_claims;
        DROP TABLE IF EXISTS agent_traces;
        DROP TABLE IF EXISTS agent_messages;
        DROP TABLE IF EXISTS agent_sessions;
        DROP TABLE IF EXISTS agent_tools;
        """
    )
