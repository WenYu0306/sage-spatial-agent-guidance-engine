"""0002：demo 数据表结构（PRD 6.1/6.2/6.4/6.5 DDL 落地，供 seed 灌虚拟商场数据）。

覆盖 11 张表：tenants、users、roles、venues、floors、map_layers、poi_categories、
pois、activities、coupons、knowledge_documents。
不包含：devices（M1）、user_roles（M1 RBAC）、route_nodes/route_edges（M3）、
coupon_claims（M8）、knowledge_chunks（M6，需 pgvector 与 embedding 维度定稿）。

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-04
"""

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# PRD 6.0 全局约定：主键 BIGINT IDENTITY；时间 TIMESTAMPTZ；枚举小写下划线；金额 NUMERIC(12,2)；
# 平面坐标 NUMERIC(10,2)（SVG 用户单位）；业务表全部带 tenant_id。
UPGRADE_SQL = """
-- ===== M1 子集：租户与账号 =====
CREATE TABLE tenants (
  id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name          VARCHAR(128) NOT NULL,
  code          VARCHAR(64)  NOT NULL UNIQUE,
  plan          VARCHAR(32)  NOT NULL DEFAULT 'demo',
  status        VARCHAR(16)  NOT NULL DEFAULT 'active',
  valid_until   DATE         NULL,
  settings      JSONB        NOT NULL DEFAULT '{}',
  created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE users (
  id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id     BIGINT       NOT NULL REFERENCES tenants(id),
  username      VARCHAR(64)  NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  display_name  VARCHAR(64)  NOT NULL,
  phone         VARCHAR(32)  NULL,
  email         VARCHAR(128) NULL,
  status        VARCHAR(16)  NOT NULL DEFAULT 'active',
  failed_logins INT          NOT NULL DEFAULT 0,
  locked_until  TIMESTAMPTZ  NULL,
  last_login_at TIMESTAMPTZ  NULL,
  created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, username)
);

CREATE TABLE roles (
  id   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  code VARCHAR(32) NOT NULL UNIQUE
);

-- ===== M2 子集：空间数据 =====
CREATE TABLE venues (
  id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id  BIGINT       NOT NULL REFERENCES tenants(id),
  name       VARCHAR(128) NOT NULL,
  venue_type VARCHAR(32)  NOT NULL DEFAULT 'mall',
  address    VARCHAR(255) NULL,
  timezone   VARCHAR(64)  NOT NULL DEFAULT 'Asia/Shanghai',
  settings   JSONB        NOT NULL DEFAULT '{}',
  status     VARCHAR(16)  NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_venues_tenant ON venues(tenant_id);

CREATE TABLE floors (
  id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id  BIGINT NOT NULL REFERENCES tenants(id),
  venue_id   BIGINT NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
  name       VARCHAR(64) NOT NULL,
  level      INT NOT NULL,
  elevation  NUMERIC(8,2) NOT NULL DEFAULT 0,
  is_default BOOLEAN NOT NULL DEFAULT false,
  sort_order INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (venue_id, level)
);

CREATE TABLE map_layers (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id   BIGINT NOT NULL REFERENCES tenants(id),
  venue_id    BIGINT NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
  floor_id    BIGINT NOT NULL REFERENCES floors(id) ON DELETE CASCADE,
  svg_url     VARCHAR(512) NOT NULL,
  width       NUMERIC(10,2) NOT NULL,
  height      NUMERIC(10,2) NOT NULL,
  scale_meter NUMERIC(10,4) NOT NULL DEFAULT 1,
  version     INT NOT NULL DEFAULT 1,
  status      VARCHAR(16) NOT NULL DEFAULT 'published',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (floor_id, version)
);

CREATE TABLE poi_categories (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id   BIGINT NOT NULL REFERENCES tenants(id),
  venue_type  VARCHAR(32) NOT NULL DEFAULT 'mall',
  code        VARCHAR(64) NOT NULL,
  name        VARCHAR(64) NOT NULL,
  parent_code VARCHAR(64) NULL,
  icon        VARCHAR(128) NULL,
  is_facility BOOLEAN NOT NULL DEFAULT false,
  searchable_by_ai BOOLEAN NOT NULL DEFAULT true,
  sort_order  INT NOT NULL DEFAULT 0,
  UNIQUE (tenant_id, venue_type, code)
);

CREATE TABLE pois (
  id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id     BIGINT NOT NULL REFERENCES tenants(id),
  venue_id      BIGINT NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
  floor_id      BIGINT NOT NULL REFERENCES floors(id),
  merchant_id   BIGINT NULL,
  category_code VARCHAR(64) NOT NULL,
  name          VARCHAR(128) NOT NULL,
  intro         TEXT NULL,
  images        JSONB NOT NULL DEFAULT '[]',
  contact       VARCHAR(64) NULL,
  position_x    NUMERIC(10,2) NOT NULL,
  position_y    NUMERIC(10,2) NOT NULL,
  geom          NUMERIC(10,2) NULL,
  business_hours JSONB NOT NULL DEFAULT '{}',
  tags          JSONB NOT NULL DEFAULT '[]',
  hot_score     NUMERIC(8,2) NOT NULL DEFAULT 0,
  recommend_weight NUMERIC(6,3) NOT NULL DEFAULT 1.0,
  status        VARCHAR(16) NOT NULL DEFAULT 'draft',
  published_at  TIMESTAMPTZ NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at    TIMESTAMPTZ NULL
);
CREATE INDEX idx_pois_tenant_venue ON pois(tenant_id, venue_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_pois_floor_cat    ON pois(floor_id, category_code) WHERE deleted_at IS NULL;
CREATE INDEX idx_pois_merchant     ON pois(merchant_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_pois_tags_gin     ON pois USING GIN (tags);

-- ===== M8 子集：内容与营销 =====
CREATE TABLE activities (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id   BIGINT NOT NULL REFERENCES tenants(id),
  venue_id    BIGINT NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
  poi_id      BIGINT NULL,
  owner_type  VARCHAR(16) NOT NULL DEFAULT 'venue',
  act_type    VARCHAR(32) NOT NULL,
  title       VARCHAR(128) NOT NULL,
  description TEXT NULL,
  images      JSONB NOT NULL DEFAULT '[]',
  start_at    TIMESTAMPTZ NOT NULL,
  end_at      TIMESTAMPTZ NOT NULL,
  status      VARCHAR(16) NOT NULL DEFAULT 'draft',
  rules       JSONB NOT NULL DEFAULT '{}',
  created_by  BIGINT NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at  TIMESTAMPTZ NULL
);
CREATE INDEX idx_act_venue_time ON activities(venue_id, start_at, end_at) WHERE deleted_at IS NULL;

CREATE TABLE coupons (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id   BIGINT NOT NULL REFERENCES tenants(id),
  venue_id    BIGINT NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
  poi_id      BIGINT NULL,
  activity_id BIGINT NULL REFERENCES activities(id) ON DELETE SET NULL,
  title       VARCHAR(128) NOT NULL,
  coupon_type VARCHAR(16) NOT NULL,
  threshold   NUMERIC(12,2) NOT NULL DEFAULT 0,
  value       NUMERIC(12,2) NOT NULL,
  total_qty   INT NOT NULL,
  claimed_qty INT NOT NULL DEFAULT 0,
  per_user_limit INT NOT NULL DEFAULT 1,
  start_at    TIMESTAMPTZ NOT NULL,
  end_at      TIMESTAMPTZ NOT NULL,
  status      VARCHAR(16) NOT NULL DEFAULT 'draft',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at  TIMESTAMPTZ NULL
);

-- ===== M6 子集：知识文档（chunks/向量表随 M6 迁移进入） =====
CREATE TABLE knowledge_documents (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id   BIGINT NOT NULL REFERENCES tenants(id),
  venue_id    BIGINT NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
  poi_id      BIGINT NULL,
  doc_type    VARCHAR(32) NOT NULL,
  title       VARCHAR(255) NOT NULL,
  content     TEXT NOT NULL,
  status      VARCHAR(16) NOT NULL DEFAULT 'active',
  version     INT NOT NULL DEFAULT 1,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def upgrade() -> None:
    from alembic import op

    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    from alembic import op

    op.execute(
        """
        DROP TABLE IF EXISTS knowledge_documents;
        DROP TABLE IF EXISTS coupons;
        DROP TABLE IF EXISTS activities;
        DROP TABLE IF EXISTS pois;
        DROP TABLE IF EXISTS poi_categories;
        DROP TABLE IF EXISTS map_layers;
        DROP TABLE IF EXISTS floors;
        DROP TABLE IF EXISTS venues;
        DROP TABLE IF EXISTS roles;
        DROP TABLE IF EXISTS users;
        DROP TABLE IF EXISTS tenants;
        """
    )
