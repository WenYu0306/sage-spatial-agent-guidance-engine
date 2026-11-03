"""0003：路网表（PRD 6.3 DDL 落地，供 M3 路径规划与路网 seed）。

route_nodes / route_edges；权重规则（PRD 6.3）：
weight = 通行时间(秒) + 惩罚项，步行 1.2 m/s、电梯惩罚 45s、扶梯 15s、
楼梯按台阶数 × 2s；无障碍模式剔除 accessible=false 的边。

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-04
"""

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

UPGRADE_SQL = """
CREATE TABLE route_nodes (
  id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id  BIGINT NOT NULL REFERENCES tenants(id),
  venue_id   BIGINT NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
  floor_id   BIGINT NOT NULL REFERENCES floors(id) ON DELETE CASCADE,
  node_type  VARCHAR(16) NOT NULL DEFAULT 'waypoint',
  poi_id     BIGINT NULL,
  x          NUMERIC(10,2) NOT NULL,
  y          NUMERIC(10,2) NOT NULL,
  accessible BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_nodes_floor ON route_nodes(floor_id);

CREATE TABLE route_edges (
  id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id      BIGINT NOT NULL REFERENCES tenants(id),
  venue_id       BIGINT NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
  from_node_id   BIGINT NOT NULL REFERENCES route_nodes(id) ON DELETE CASCADE,
  to_node_id     BIGINT NOT NULL REFERENCES route_nodes(id) ON DELETE CASCADE,
  edge_type      VARCHAR(16) NOT NULL DEFAULT 'walk',
  distance_meter NUMERIC(8,2) NOT NULL,
  weight         NUMERIC(10,3) NOT NULL,
  accessible     BOOLEAN NOT NULL DEFAULT true,
  is_bidirectional BOOLEAN NOT NULL DEFAULT true,
  UNIQUE (from_node_id, to_node_id, edge_type)
);
CREATE INDEX idx_edges_from ON route_edges(from_node_id);
CREATE INDEX idx_edges_to   ON route_edges(to_node_id);
"""


def upgrade() -> None:
    from alembic import op

    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    from alembic import op

    op.execute("DROP TABLE IF EXISTS route_edges; DROP TABLE IF EXISTS route_nodes;")
