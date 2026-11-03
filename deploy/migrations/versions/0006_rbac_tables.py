"""0006：RBAC 与审计表（PRD 6.1 DDL 落地，M1 完整 RBAC 的数据层）。

user_roles / devices / operation_logs。
偏差说明：PRD 的 user_roles 主键 (user_id, role_id, venue_id) 与 venue_id 可空矛盾
（PostgreSQL 主键列不可为 NULL）。实现改为表达式唯一索引
UNIQUE (user_id, role_id, COALESCE(venue_id,0), COALESCE(merchant_id,0))，
语义等价：同一用户同一角色在同一（场地, 门店）范围内只允许一条绑定，
NULL 范围（租户全局）也参与唯一性。已记 DECISIONS D-019。

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-04
"""

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

UPGRADE_SQL = """
CREATE TABLE user_roles (
  user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role_id     BIGINT NOT NULL REFERENCES roles(id),
  venue_id    BIGINT NULL,              -- 角色绑定的场地范围，NULL 表示租户全局
  merchant_id BIGINT NULL,              -- merchant 角色绑定的门店（pois.id）
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_user_roles_scope ON user_roles(
  user_id, role_id, COALESCE(venue_id, 0), COALESCE(merchant_id, 0));
CREATE INDEX idx_user_roles_user ON user_roles(user_id);

CREATE TABLE devices (
  id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id     BIGINT       NOT NULL REFERENCES tenants(id),
  venue_id      BIGINT       NOT NULL,
  floor_id      BIGINT       NULL,
  code          VARCHAR(64)  NOT NULL,
  name          VARCHAR(128) NOT NULL,
  device_type   VARCHAR(16)  NOT NULL DEFAULT 'screen',  -- screen/kiosk/mobile
  position_x    NUMERIC(10,2) NULL,                      -- 该设备所在位置（路径规划起点）
  position_y    NUMERIC(10,2) NULL,
  status        VARCHAR(16)  NOT NULL DEFAULT 'offline', -- online/offline/maintenance
  app_version   VARCHAR(32)  NULL,
  last_seen_at  TIMESTAMPTZ  NULL,
  created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, code)
);
CREATE INDEX idx_devices_venue ON devices(venue_id);

CREATE TABLE operation_logs (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id   BIGINT NOT NULL,
  user_id     BIGINT NULL,
  action      VARCHAR(48) NOT NULL,             -- create/update/delete/publish/login
  object_type VARCHAR(32) NOT NULL,
  object_id   BIGINT NULL,
  diff        JSONB NULL,
  ip          VARCHAR(64) NULL,
  trace_id    VARCHAR(64) NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_oplogs_tenant_time ON operation_logs(tenant_id, created_at);
"""


def upgrade() -> None:
    from alembic import op

    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    from alembic import op

    op.execute(
        "DROP TABLE IF EXISTS operation_logs; DROP TABLE IF EXISTS devices; "
        "DROP TABLE IF EXISTS user_roles;"
    )
