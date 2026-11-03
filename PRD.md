# 空间智能体导视平台 PRD v1（Production-First）

> 配套文档：`空间智能体导视平台-架构与模块契约-v1.md`（架构、模块边界、工程约定、排期）。
> 本文档定位：**可直接交给 Claude Code 执行的生产级需求规格**。按真实上线标准编写（含权限矩阵、DDL、API Schema、异常与降级、并发、安全、容灾、成本、部署、验收），demo 阶段允许降级实现，但**接口契约、数据结构、权限模型不得简化**，以保证 demo 可平滑转生产。

---

## 1. 产品定位

**一句话**：面向多场地运营方的 AI 空间导视与商业运营平台，顾客通过大屏或手机用自然语言获得问答、推荐与室内外路线，运营方通过后台维护空间数据与营销内容并查看经营数据。

**产品形态**：多租户 SaaS。一个租户 = 一个运营方；一个运营方可管理多个场地（venue，如商场/医院/园区）；每个场地有独立空间数据、内容、设备与统计。

**首批量级（demo）**：1 个租户、2 个场地（1 个有完整数据、1 个空数据用于验证多场地隔离）、3 层楼、60—80 个 POI、20 个公共设施、10 个活动/优惠、1 块大屏模拟页、手机端 H5。

**生产目标量级（设计承载）**：100 个场地、单场地 20 块大屏、日活顾客 5000、日问答 3000 次、峰值见第 11 节。

**参考形态**：商场智能导视大屏 + 室内导航 H5 + AI 问答（RAG + 工具调用）。

---

## 2. 用户角色与权限矩阵

### 2.1 角色定义

| 角色 | 标识 | 说明 |
| :--- | :--- | :--- |
| 平台超级管理员 | `platform_admin` | 平台运营方，管理所有租户、场地、设备、系统配置、套餐与有效期 |
| 商场运营管理员 | `venue_admin` | 单租户下某场地的运营负责人，管理本场地全部内容 |
| 商场运营编辑 | `venue_editor` | 只能编辑内容与地图，不能管账号、不能改配置 |
| 商户 | `merchant` | 只能管理自己门店的资料、活动、优惠，查看自己的引流数据 |
| 设备 | `device` | 大屏/终端的机器身份，只能上报状态、拉取配置、发起问答 |
| 顾客 | `guest` | 无需登录，手机端匿名使用，以 `anonymous_id` 标识 |

### 2.2 权限矩阵（角色 × 功能 × 数据范围）

| 功能 | platform_admin | venue_admin | venue_editor | merchant | device | guest |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 租户/场地增删改 | 全部 | 只读本场地的场地信息 | 无 | 无 | 无 | 无 |
| 账号与角色管理 | 全部 | 本场地 | 无 | 无 | 无 | 无 |
| 楼层与地图图层维护 | 全部 | 本场地 | 本场地 | 无 | 无 | 无 |
| POI/设施 CRUD | 全部 | 本场地 | 本场地 | 仅自己门店 POI | 无 | 只读（通过问答） |
| 活动/优惠 CRUD | 全部 | 本场地 | 本场地 | 仅自己门店的活动优惠 | 无 | 只读 |
| AI 知识内容维护 | 全部 | 本场地 | 本场地 | 无 | 无 | 无 |
| 推荐权重配置 | 全部 | 本场地 | 无 | 无 | 无 | 无 |
| 设备管理 | 全部（含启停） | 本场地只读 | 无 | 无 | 仅自身状态上报 | 无 |
| 数据看板 | 全部租户 | 本场地 | 本场地（只读） | 仅自己门店引流数据 | 无 | 无 |
| 发起 AI 问答 | 是 | 是 | 是 | 是 | 是 | 是 |
| 系统配置/套餐/有效期 | 全部 | 无 | 无 | 无 | 无 | 无 |

**数据范围强制规则**：所有查询必须在服务层注入 `tenant_id` 与 `venue_id` 过滤条件，禁止依赖前端传参决定数据范围。商户额外注入 `merchant_id` 过滤。**越权访问必须返回 `1003`，不得返回空列表伪装成功**（否则前端无法区分"无数据"与"无权限"）。

### 2.3 越权测试用例（必须实现为自动化测试）

1. `venue_editor` 调用账号管理接口 → 403 / `1003`
2. A 场地的 `venue_admin` 用 URL 参数改成 B 场地 ID 查 POI → 403 / `1003`
3. 商户 A 修改商户 B 的门店资料 → 403 / `1003`
4. `guest` 直接访问 `/api/v1/admin/*` → 401 / `1001`
5. 设备 token 调用内容写接口 → 403 / `1003`

---

## 3. 核心业务流程

### 3.1 顾客问路（主流程，最高频）

```
顾客在大屏输入/说出"卫生间在哪里"
→ 大屏 POST /api/v1/agent/chat（携带 tenant_id/venue_id/device_id/session_id/当前楼层）
→ M5 解析意图 = facility.nearest
→ 调工具 facility.nearest(type=toilet, from=当前大屏位置)
→ M2 空间查询候选 → M3 规划路线（同层或跨层）
→ M5 生成回答 + 路线卡片，SSE 流式返回
→ 大屏渲染路线（M4），显示分段、距离、预计耗时
→ 顾客点"发到手机" → 大屏生成二维码（含 session_id + route_id）
→ 手机扫码打开 H5 → GET /api/v1/route/{route_id} → 继续查看路线
→ 全链路事件写入 M9（问答、导航、扫码接力）
```

**关键约束**：从顾客提交到首字返回 ≤2s（流式）；完整回答 ≤8s；超时必须有兜底（见第 10 节）。

### 3.2 顾客找吃的（推荐流程）

```
"有没有适合情侣吃饭的地方"
→ 意图 = poi_recommend，抽取 {category: 餐厅, scene: date}
→ poi.search（营业中 + 分类 + 场景标签）
→ promotion.list（这些 POI 的当前优惠）
→ knowledge.query（店铺特色，带出处）
→ recommend.rank（8 因子打分 + 理由）
→ route.plan（Top1 预算路线）
→ 返回：推荐列表（每项含理由标签、优惠、距离）+ Top1 路线入口
```

### 3.3 运营维护内容（后台流程）

```
venue_editor 登录 → 选场地 → 楼层管理（新增楼层 + 上传底图 SVG）
→ 点位标注（M4 PoiPicker 在底图点击生成 POI，填 8 项字段）
→ 提交 → venue_admin 审核（状态机 draft → pending → published）
→ published 后：M2 空间索引更新 + M6 知识重新索引 + M3 路网按需重建
→ 顾客下一次问答即可命中新数据（要求：无需重启服务）
```

**验收要点**：内容发布到 AI 可感知，端到端 ≤60 秒。

### 3.4 经营数据查看

```
venue_admin 登录 → 数据看板 → 选时间范围/楼层/设备
→ M9 返回 11 项指标 → 图表渲染
→ 可下钻：点"店铺搜索排行"某一项 → 看该店被搜索的时间分布与后续导航转化
```

---

## 4. 功能范围分级

### 4.1 P0（V1 必须有，不做就不能算完成）

| 编号 | 功能 | 模块 |
| :--- | :--- | :--- |
| F-01 | 多租户与多场地数据隔离 | M1/M2 |
| F-02 | 四角色 RBAC 鉴权与越权拦截 | M1 |
| F-03 | 楼层与地图图层管理（SVG 底图上传、缩放拖动、楼层切换） | M2/M4 |
| F-04 | POI 与公共设施管理（14 类地点、8 项字段、复合查询） | M2/M8 |
| F-05 | 点位标注工具（底图点击生成坐标） | M4/M10 |
| F-06 | 路网构建与跨楼层路径规划（含无障碍、距离与耗时） | M3 |
| F-07 | AI 自然语言问答（意图解析 + 工具调用 + 多轮上下文 + 流式输出） | M5 |
| F-08 | 调用链 trace 落库与可视化查询 | M5 |
| F-09 | 知识 RAG（入库、切片、检索、出处、幻觉控制） | M6 |
| F-10 | 活动与优惠管理（8 类活动、优惠券领取与幂等） | M8 |
| F-11 | 手机扫码接力导航 | M11/M12 |
| F-12 | 商场运营后台（内容维护、地图维护、账号管理） | M10 |
| F-13 | AI 不可用/超时的降级兜底 | M5/M6 |
| F-14 | 容器化部署、环境分离、数据库迁移、健康检查、备份 | M13 |
| F-15 | 埋点采集（事件入库） | M1/M9 |

### 4.2 P1（V1 尽量有，可简化实现）

| 编号 | 功能 | 简化实现方式 |
| :--- | :--- | :--- |
| F-16 | 8 因子推荐排序 + 可解释理由 | 权重固定配置文件，不做后台可调 |
| F-17 | 大屏端 UI | 用 H5 全屏页模拟，不做 Android 原生 |
| F-18 | 11 项指标看板 | 先做 6 项核心指标，其余留接口 |
| F-19 | 设备管理（注册、在线状态、版本） | 只读列表 + 心跳上报，不做远程控制 |
| F-20 | 广告位与闲置轮播 | 后台可配图片与时间，不做定向投放 |

### 4.3 P2（V2，明确不做）

摄像头人体检测与靠近唤醒、手势交互、数字人与口型同步、多语言、个性化推荐（协同过滤/用户画像）、设备 OTA 远程更新与重启、商户独立后台、优惠券核销完整闭环（V1 只做领取与状态记录）、手机实时室内定位（蓝点）、支付与交易、跨租户数据看板、开放 API 与第三方接入、离线包与弱网优化。

---

## 5. 非功能需求

| 类别 | 指标 |
| :--- | :--- |
| 性能 | 普通查询接口 P95 < 300ms；路径规划 P95 < 200ms；AI 问答首字 < 2s、完整 < 8s；后台列表页 P95 < 800ms |
| 可用性 | demo 环境 99%；生产目标 99.5%；单模块故障不导致全站不可用（降级见第 10 节） |
| 并发 | 见第 11 节测算 |
| 安全 | 全站 HTTPS；密码 bcrypt（cost ≥12）；SQL 全部参数化；前端输出转义；上传文件类型与大小校验；日志脱敏；租户隔离自动化测试覆盖 |
| 可观测 | 结构化日志（JSON）；trace_id 全链路贯穿；关键指标（QPS、错误率、AI 超时率、慢查询）可查 |
| 可维护 | 数据库变更 100% 走迁移；配置 100% 外置；模块可独立启动与测试 |
| 兼容 | Chrome/Edge/Safari 近两年版本；微信内置浏览器；大屏 1080p 与 4K；手机 375—430px 宽 |
| 数据保留 | 埋点明细保留 180 天，日聚合永久；Agent trace 保留 90 天；操作日志保留 1 年 |

---

## 6. 数据模型（PostgreSQL 16 + PostGIS + pgvector）

### 6.0 全局约定

- 主键：`id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`
- 时间：`created_at / updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`，存 UTC
- 软删除：`deleted_at TIMESTAMPTZ NULL`（内容类表用，日志类表不用）
- 枚举：统一小写下划线字符串（`draft`/`pending`/`published`）
- 多租户：业务表全部含 `tenant_id BIGINT NOT NULL`，并建复合索引前缀
- 金额：`NUMERIC(12,2)`，禁止 float
- 坐标：平面坐标用 `NUMERIC(10,2)` 的 `x/y`（SVG 用户单位）；如需地理坐标另加 PostGIS `geometry(Point,4326)`

### 6.1 租户与账号（M1）

```sql
CREATE TABLE tenants (
  id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name          VARCHAR(128) NOT NULL,
  code          VARCHAR(64)  NOT NULL UNIQUE,          -- 租户编码，用于配置与日志
  plan          VARCHAR(32)  NOT NULL DEFAULT 'demo',  -- demo/standard/enterprise
  status        VARCHAR(16)  NOT NULL DEFAULT 'active',-- active/suspended/expired
  valid_until   DATE         NULL,                     -- 套餐有效期
  settings      JSONB        NOT NULL DEFAULT '{}',
  created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE users (
  id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id     BIGINT       NOT NULL REFERENCES tenants(id),
  username      VARCHAR(64)  NOT NULL,
  password_hash VARCHAR(255) NOT NULL,                 -- bcrypt, cost>=12
  display_name  VARCHAR(64)  NOT NULL,
  phone         VARCHAR(32)  NULL,
  email         VARCHAR(128) NULL,
  status        VARCHAR(16)  NOT NULL DEFAULT 'active',-- active/disabled/locked
  failed_logins INT          NOT NULL DEFAULT 0,
  locked_until  TIMESTAMPTZ  NULL,
  last_login_at TIMESTAMPTZ  NULL,
  created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, username)
);

CREATE TABLE roles (
  id     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  code   VARCHAR(32) NOT NULL UNIQUE  -- platform_admin/venue_admin/venue_editor/merchant/device
);

CREATE TABLE user_roles (
  user_id   BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role_id   BIGINT NOT NULL REFERENCES roles(id),
  venue_id  BIGINT NULL,              -- 角色绑定的场地范围，NULL 表示租户全局
  merchant_id BIGINT NULL,            -- merchant 角色绑定的门店
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- 2026-11-04 修订：原主键 (user_id, role_id, venue_id) 含可空列（PG 主键列不可 NULL），
-- 按表达式唯一索引实现同一"用户×角色×范围唯一"语义（0006 实装一致，见 D-019）。
CREATE UNIQUE INDEX uq_user_roles_scope ON user_roles(
  user_id, role_id, COALESCE(venue_id, 0), COALESCE(merchant_id, 0));

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
```

### 6.2 空间数据（M2）

```sql
CREATE TABLE venues (
  id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id     BIGINT       NOT NULL REFERENCES tenants(id),
  name          VARCHAR(128) NOT NULL,
  venue_type    VARCHAR(32)  NOT NULL DEFAULT 'mall',   -- mall/hospital/campus/park/scenic
  address       VARCHAR(255) NULL,
  timezone      VARCHAR(64)  NOT NULL DEFAULT 'Asia/Shanghai',
  settings      JSONB        NOT NULL DEFAULT '{}',     -- 营业时间、默认楼层、欢迎语
  status        VARCHAR(16)  NOT NULL DEFAULT 'active',
  created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_venues_tenant ON venues(tenant_id);

CREATE TABLE floors (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id   BIGINT NOT NULL REFERENCES tenants(id),
  venue_id    BIGINT NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
  name        VARCHAR(64) NOT NULL,            -- "F1"/"B1"
  level       INT NOT NULL,                    -- 排序与跨层计算用，B1=-1
  elevation   NUMERIC(8,2) NOT NULL DEFAULT 0, -- 相对高度（米），用于耗时估算
  is_default  BOOLEAN NOT NULL DEFAULT false,
  sort_order  INT NOT NULL DEFAULT 0,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (venue_id, level)
);

CREATE TABLE map_layers (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id   BIGINT NOT NULL REFERENCES tenants(id),
  venue_id    BIGINT NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
  floor_id    BIGINT NOT NULL REFERENCES floors(id) ON DELETE CASCADE,
  svg_url     VARCHAR(512) NOT NULL,           -- 底图存储地址
  width       NUMERIC(10,2) NOT NULL,          -- SVG viewBox 宽
  height      NUMERIC(10,2) NOT NULL,
  scale_meter NUMERIC(10,4) NOT NULL DEFAULT 1,-- 1 SVG 单位 = ? 米，用于距离换算
  version     INT NOT NULL DEFAULT 1,
  status      VARCHAR(16) NOT NULL DEFAULT 'published',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (floor_id, version)
);

CREATE TABLE poi_categories (              -- 数据字典：换场景只改这张表
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id   BIGINT NOT NULL REFERENCES tenants(id),
  venue_type  VARCHAR(32) NOT NULL DEFAULT 'mall',
  code        VARCHAR(64) NOT NULL,          -- restaurant/toilet/cinema/elevator...
  name        VARCHAR(64) NOT NULL,
  parent_code VARCHAR(64) NULL,
  icon        VARCHAR(128) NULL,
  is_facility BOOLEAN NOT NULL DEFAULT false,-- 设施类不参与推荐排序
  searchable_by_ai BOOLEAN NOT NULL DEFAULT true,
  sort_order  INT NOT NULL DEFAULT 0,
  UNIQUE (tenant_id, venue_type, code)
);

CREATE TABLE pois (
  id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id     BIGINT NOT NULL REFERENCES tenants(id),
  venue_id      BIGINT NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
  floor_id      BIGINT NOT NULL REFERENCES floors(id),
  merchant_id   BIGINT NULL,                 -- 归属商户，NULL 表示场地方自营/公共设施
  category_code VARCHAR(64) NOT NULL,
  name          VARCHAR(128) NOT NULL,
  intro         TEXT NULL,
  images        JSONB NOT NULL DEFAULT '[]',
  contact       VARCHAR(64) NULL,
  position_x    NUMERIC(10,2) NOT NULL,
  position_y    NUMERIC(10,2) NOT NULL,
  geom          NUMERIC(10,2) NULL,          -- 预留 PostGIS 字段位（见 PRD 附录说明）
  business_hours JSONB NOT NULL DEFAULT '{}',-- {"mon":["10:00-22:00"],...,"holidays":[]}
  tags          JSONB NOT NULL DEFAULT '[]', -- ["约会","亲子","安静"]，AI 场景匹配用
  hot_score     NUMERIC(8,2) NOT NULL DEFAULT 0,
  recommend_weight NUMERIC(6,3) NOT NULL DEFAULT 1.0,  -- 商户推荐权重
  status        VARCHAR(16) NOT NULL DEFAULT 'draft',  -- draft/pending/published/offline
  published_at  TIMESTAMPTZ NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at    TIMESTAMPTZ NULL
);
CREATE INDEX idx_pois_tenant_venue ON pois(tenant_id, venue_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_pois_floor_cat    ON pois(floor_id, category_code) WHERE deleted_at IS NULL;
CREATE INDEX idx_pois_merchant     ON pois(merchant_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_pois_tags_gin     ON pois USING GIN (tags);

-- 公共设施与 POI 同表，用 poi_categories.is_facility=true 区分，避免两套模型
```

### 6.3 路网（M3）

```sql
CREATE TABLE route_nodes (
  id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id  BIGINT NOT NULL REFERENCES tenants(id),
  venue_id   BIGINT NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
  floor_id   BIGINT NOT NULL REFERENCES floors(id) ON DELETE CASCADE,
  node_type  VARCHAR(16) NOT NULL DEFAULT 'waypoint', -- waypoint/entrance/elevator/escalator/stairs/poi_link
  poi_id     BIGINT NULL,                   -- node_type=poi_link 时关联的 POI
  x          NUMERIC(10,2) NOT NULL,
  y          NUMERIC(10,2) NOT NULL,
  accessible BOOLEAN NOT NULL DEFAULT true, -- 是否无障碍可达
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_nodes_floor ON route_nodes(floor_id);

CREATE TABLE route_edges (
  id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id      BIGINT NOT NULL REFERENCES tenants(id),
  venue_id       BIGINT NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
  from_node_id   BIGINT NOT NULL REFERENCES route_nodes(id) ON DELETE CASCADE,
  to_node_id     BIGINT NOT NULL REFERENCES route_nodes(id) ON DELETE CASCADE,
  edge_type      VARCHAR(16) NOT NULL DEFAULT 'walk',  -- walk/elevator/escalator/stairs/ramp
  distance_meter NUMERIC(8,2) NOT NULL,
  weight         NUMERIC(10,3) NOT NULL,   -- 通行代价（含垂直交通等待时间）
  accessible     BOOLEAN NOT NULL DEFAULT true,
  is_bidirectional BOOLEAN NOT NULL DEFAULT true,
  UNIQUE (from_node_id, to_node_id, edge_type)
);
CREATE INDEX idx_edges_from ON route_edges(from_node_id);
CREATE INDEX idx_edges_to   ON route_edges(to_node_id);
```

**权重设计规则**（写入 DECISIONS.md）：`weight = 通行时间(秒) + 惩罚项`。步行按 1.2 m/s；电梯固定惩罚 45s（等待+进出）；扶梯惩罚 15s；楼梯按台阶数 × 2s；无障碍模式下 `accessible=false` 的边直接剔除；跨层边必须连接不同 `floor_id` 的节点。

### 6.4 内容与营销（M8）

```sql
CREATE TABLE activities (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id   BIGINT NOT NULL REFERENCES tenants(id),
  venue_id    BIGINT NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
  poi_id      BIGINT NULL,                    -- NULL 表示商场级活动
  owner_type  VARCHAR(16) NOT NULL DEFAULT 'venue', -- venue/brand/shop
  act_type    VARCHAR(32) NOT NULL,           -- mall_activity/brand_activity/shop_promo/coupon/full_reduction/package/flash_sale/new_store
  title       VARCHAR(128) NOT NULL,
  description TEXT NULL,
  images      JSONB NOT NULL DEFAULT '[]',
  start_at    TIMESTAMPTZ NOT NULL,
  end_at      TIMESTAMPTZ NOT NULL,
  status      VARCHAR(16) NOT NULL DEFAULT 'draft', -- draft/pending/active/ended/archived
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
  coupon_type VARCHAR(16) NOT NULL,           -- discount/full_reduction/gift
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

CREATE TABLE coupon_claims (
  id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id     BIGINT NOT NULL REFERENCES tenants(id),
  coupon_id     BIGINT NOT NULL REFERENCES coupons(id) ON DELETE CASCADE,
  anonymous_id  VARCHAR(64) NOT NULL,          -- 顾客标识（demo 用设备指纹/随机ID）
  claim_status  VARCHAR(16) NOT NULL DEFAULT 'claimed', -- claimed/used/expired
  claimed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  used_at       TIMESTAMPTZ NULL,
  idempotency_key VARCHAR(128) NOT NULL UNIQUE -- 幂等键：coupon_id + anonymous_id
);
CREATE INDEX idx_claims_coupon ON coupon_claims(coupon_id);
```

### 6.5 知识与 AI（M6/M5）

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE knowledge_documents (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id   BIGINT NOT NULL REFERENCES tenants(id),
  venue_id    BIGINT NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
  poi_id      BIGINT NULL,
  doc_type    VARCHAR(32) NOT NULL,           -- poi_intro/venue_guide/faq/policy/activity
  title       VARCHAR(255) NOT NULL,
  content     TEXT NOT NULL,
  status      VARCHAR(16) NOT NULL DEFAULT 'active',
  version     INT NOT NULL DEFAULT 1,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE knowledge_chunks (
  id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  document_id BIGINT NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
  tenant_id  BIGINT NOT NULL,
  venue_id   BIGINT NOT NULL,
  chunk_index INT NOT NULL,
  content    TEXT NOT NULL,
  token_count INT NOT NULL,
  embedding  vector(1024),                     -- 维度按所选 embedding 模型调整
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (document_id, chunk_index)
);
CREATE INDEX idx_chunks_embedding ON knowledge_chunks USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX idx_chunks_venue ON knowledge_chunks(tenant_id, venue_id);

CREATE TABLE agent_tools (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  code        VARCHAR(64) NOT NULL UNIQUE,     -- poi.search / route.plan ...
  name        VARCHAR(128) NOT NULL,
  description TEXT NOT NULL,                   -- 给模型看的工具说明
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
  channel     VARCHAR(16) NOT NULL DEFAULT 'screen', -- screen/mobile/admin
  status      VARCHAR(16) NOT NULL DEFAULT 'active', -- active/closed/handed_over
  handed_to_session_id BIGINT NULL,            -- 手机接力时关联
  started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_active_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE agent_messages (
  id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  session_id BIGINT NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
  tenant_id  BIGINT NOT NULL,
  role       VARCHAR(16) NOT NULL,             -- user/assistant/system/tool
  content    TEXT NOT NULL,
  structured JSONB NULL,                       -- 卡片数据：poi列表/路线/优惠/引用
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
  step_type   VARCHAR(32) NOT NULL,            -- intent_parse/tool_call/rag_query/rank/generate
  tool_code   VARCHAR(64) NULL,
  input       JSONB NULL,
  output      JSONB NULL,
  status      VARCHAR(16) NOT NULL,            -- ok/timeout/error/degraded
  latency_ms  INT NOT NULL,
  error_code  INT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_trace_msg ON agent_traces(message_id, step_index);
CREATE INDEX idx_trace_tid ON agent_traces(trace_id);
```

### 6.6 埋点与指标（M9）

```sql
CREATE TABLE events (
  id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id    BIGINT NOT NULL,
  venue_id     BIGINT NOT NULL,
  event_id     VARCHAR(64) NOT NULL UNIQUE,    -- 客户端生成，幂等去重
  event_type   VARCHAR(48) NOT NULL,           -- 见第 15 节事件字典
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
  metric_code VARCHAR(48) NOT NULL,            -- ai_query_count/search_count/...
  dim_type    VARCHAR(32) NOT NULL DEFAULT 'venue', -- venue/floor/device/poi/hour
  dim_value   VARCHAR(64) NOT NULL DEFAULT 'all',
  value       NUMERIC(16,2) NOT NULL,
  UNIQUE (venue_id, metric_date, metric_code, dim_type, dim_value)
);

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

CREATE TABLE operation_logs (
  id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id  BIGINT NOT NULL,
  user_id    BIGINT NULL,
  action     VARCHAR(48) NOT NULL,             -- create/update/delete/publish/login
  object_type VARCHAR(32) NOT NULL,
  object_id  BIGINT NULL,
  diff       JSONB NULL,
  ip         VARCHAR(64) NULL,
  trace_id   VARCHAR(64) NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

## 7. API 规格

### 7.0 通用约定

- 前缀 `/api/v1`；资源名复数；层级 `/api/v1/{模块}/{资源}`
- 必带请求头：`Authorization`（guest 除外）、`X-Tenant-Id`、`X-Trace-Id`、`X-Client`（admin/screen/mobile）、`X-Device-Id`（大屏与手机端必带）
- 统一响应体与错误码见 ARCHITECTURE.md 第 8 节
- 分页：`?page=1&page_size=20`，响应 `data.items` + `data.total`
- 所有写接口必须幂等：客户端可传 `Idempotency-Key`，服务端 24 小时内相同 key 返回首次结果
- 限流：guest 每 IP 每分钟 30 次问答；后台每用户每分钟 300 次；超限返回 `9002`

### 7.1 Agent 问答（M5，核心接口）

`POST /api/v1/agent/chat`（SSE 流式，角色：全部含 guest）

请求体 Schema：

| 字段 | 类型 | 必填 | 校验 |
| :--- | :--- | :--- | :--- |
| session_id | string | 否 | 为空则服务端新建会话并回传 |
| venue_id | int | 是 | 必须属于当前租户 |
| device_id | int | 大屏必填 | 必须属于该 venue |
| floor_id | int | 否 | 用户当前楼层，路径规划起点用 |
| message | string | 是 | 1—500 字，超长返回 422 |
| anonymous_id | string | 否 | 手机端标识，最长 64 |
| context | object | 否 | `{position_x, position_y, prefer_accessible}` |

请求示例：

```json
{
  "venue_id": 1,
  "device_id": 3,
  "floor_id": 2,
  "message": "有没有适合情侣吃饭的地方，最好有优惠",
  "context": {"position_x": 512.0, "position_y": 300.5, "prefer_accessible": false}
}
```

响应（SSE 事件流，每条为一个 JSON）：

```
event: meta
data: {"session_id": 88, "message_id": 1024, "trace_id": "tr_x1"}

event: delta
data: {"text": "为你找到 3 家"}

event: card
data: {"type":"poi_list","items":[{"poi_id":12,"name":"XX餐厅","floor":"F3","distance_meter":180,"eta_seconds":190,"reasons":["距你180米","营业中","满100减20"],"coupon":{"title":"满100减20","coupon_id":5}}]}

event: card
data: {"type":"route","route_id":301,"summary":{"distance_meter":180,"eta_seconds":190,"floors":["F2","F3"],"transfers":[{"type":"escalator","from":"F2","to":"F3"}]}}

event: citations
data: {"items":[{"document_id":9,"title":"店铺介绍","snippet":"……"}]}

event: done
data: {"status":"ok","latency_ms":3120,"degraded":false}
```

失败与降级响应：`event: done` 中 `status` 为 `degraded`（AI 不可用，已回退关键词检索，`error_code=3004`）或 `error`（`error_code=3001`，返回兜底话术卡片 + 楼层平面图入口）。

`GET /api/v1/agent/sessions/{session_id}/trace`（角色：platform_admin/venue_admin，作品集演示用）→ 返回该会话每条消息的完整 `agent_traces` 步骤序列。

### 7.2 路径规划（M3）

`POST /api/v1/route/plan`（角色：全部含 guest 与 device）

| 字段 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| venue_id | int | 是 | |
| from | object | 是 | `{floor_id, x, y}` 或 `{poi_id}` 或 `{device_id}` |
| to | object | 是 | `{poi_id}` 或 `{floor_id, x, y}` |
| waypoints | array | 否 | 途经点，最多 3 个 |
| prefer_accessible | bool | 否 | 默认 false；true 时剔除楼梯与非无障碍边 |

响应示例：

```json
{
  "code": 0,
  "data": {
    "route_id": 301,
    "distance_meter": 180.5,
    "eta_seconds": 190,
    "accessible": false,
    "segments": [
      {"floor_id": 2, "floor_name": "F2", "mode": "walk", "distance_meter": 60.0, "eta_seconds": 50,
       "path": [{"x": 512.0, "y": 300.5}, {"x": 640.0, "y": 300.5}]},
      {"floor_id": 2, "floor_name": "F2", "mode": "escalator", "distance_meter": 0, "eta_seconds": 15,
       "to_floor_id": 3, "node_id": 77},
      {"floor_id": 3, "floor_name": "F3", "mode": "walk", "distance_meter": 120.5, "eta_seconds": 100,
       "path": [{"x": 640.0, "y": 300.5}, {"x": 810.0, "y": 420.0}]}
    ],
    "expires_at": "2026-11-03T21:30:00Z"
  }
}
```

`GET /api/v1/route/{route_id}`：手机接力用，返回同上结构（route 结果需缓存，TTL 30 分钟）。
`POST /api/v1/route/graph/rebuild`（角色：venue_admin）：地图或路网变更后重建图，返回任务 ID；重建期间路径接口返回 `2004` 并触发降级。

### 7.3 空间与内容（M2/M8）

| 方法 | 路径 | 说明 | 角色 |
| :--- | :--- | :--- | :--- |
| GET | /api/v1/venues | 场地列表（按租户） | platform_admin/venue_admin |
| GET | /api/v1/venues/{id}/floors | 楼层列表 | 全部 |
| GET | /api/v1/floors/{id}/map-layer | 当前版本底图与尺寸、比例尺 | 全部 |
| GET | /api/v1/pois | POI 列表，支持 `category_code/floor_id/status/keyword/tags/open_now/merchant_id` 组合过滤 + 分页 | 按权限 |
| GET | /api/v1/pois/{id} | POI 详情（含营业时间、当前活动与优惠） | 全部 |
| POST/PATCH/DELETE | /api/v1/pois | 创建/更新/软删除 | venue_admin/venue_editor/merchant（仅自己门店） |
| POST | /api/v1/pois/{id}/publish | 提交发布（状态机流转） | venue_admin |
| GET/POST/PATCH | /api/v1/activities | 活动管理，过滤 `act_type/status/poi_id/time_range` | 同上 |
| GET | /api/v1/coupons | 优惠券列表，含剩余量 | 全部 |
| POST | /api/v1/coupons/{id}/claim | 领取（幂等键 = coupon_id + anonymous_id） | guest |
| GET/POST/PATCH/DELETE | /api/v1/knowledge-documents | 知识内容管理 | venue_admin/venue_editor |
| GET | /api/v1/categories | POI 分类字典（按 venue_type） | 全部 |
| GET/POST | /api/v1/route-nodes、/api/v1/route-edges | 路网维护 | venue_admin/venue_editor |

创建 POI 请求示例：

```json
{
  "venue_id": 1, "floor_id": 3, "category_code": "restaurant",
  "name": "示例餐厅", "intro": "主打川菜，环境安静适合小聚",
  "position_x": 810.0, "position_y": 420.0,
  "business_hours": {"mon": ["10:00-22:00"], "sun": ["10:00-22:30"]},
  "tags": ["约会", "安静"], "images": [{"url": "https://.../a.jpg", "sort": 1}],
  "contact": "0431-8888****"
}
```

### 7.4 统计与设备（M9/M1）

| 方法 | 路径 | 说明 | 角色 |
| :--- | :--- | :--- | :--- |
| POST | /api/v1/events | 批量上报埋点（数组，单次 ≤50 条，按 event_id 幂等） | 全部含 device/guest |
| GET | /api/v1/metrics/overview | 概览指标，参数 `date_from/date_to/floor_id/device_id` | venue_admin/venue_editor |
| GET | /api/v1/metrics/{code} | 单指标时序，参数 `granularity=day|hour` | 同上 |
| GET | /api/v1/metrics/merchant/{poi_id} | 商户维度引流数据（被搜索/被推荐/导航到店/领券） | merchant |
| GET | /api/v1/devices | 设备列表与在线状态 | platform_admin/venue_admin |
| POST | /api/v1/devices/{id}/heartbeat | 设备心跳（更新 last_seen_at、status、app_version） | device |
| POST | /api/v1/auth/login | 登录（返回 access + refresh token） | 全部后台角色 |
| POST | /api/v1/auth/refresh | 刷新 token | 同上 |

### 7.5 冻结能力占位接口

`POST /api/v1/voice/transcribe`、`POST /api/v1/voice/synthesize`、`POST /api/v1/avatar/render`：V1 全部返回 `5001`/`5002`（能力未启用），但**路由与 Schema 必须存在**，以保证将来接入不改端层代码。

---

## 8. AI 能力规格（M5/M6/M7）

### 8.1 意图体系（V1 支持 8 类）

| intent | 触发示例 | 调用工具链 |
| :--- | :--- | :--- |
| facility_nearest | "卫生间在哪里" | facility.nearest → route.plan |
| poi_search | "哪里可以买衣服" | poi.search → recommend.rank |
| poi_recommend | "有没有适合情侣吃饭的地方" | poi.search → promotion.list → knowledge.query → recommend.rank → route.plan |
| promotion_query | "今天有什么优惠" | promotion.list → poi.detail |
| navigate | "带我去电影院" | poi.search(唯一匹配) → route.plan |
| venue_info | "商场几点关门" | knowledge.query |
| coupon_claim | "帮我领这张券" | coupon.claim |
| fallback | 无法归类 | knowledge.query → 无结果则兜底话术 |

**实现要求**：意图解析必须由模型输出结构化 JSON（用 JSON Schema 约束 + 校验失败重试 1 次），禁止用正则匹配关键词硬编码。解析结果写入 `agent_traces.step_type='intent_parse'`。

### 8.2 工具注册表（V1 八个工具）

| code | 说明（给模型的描述） | 超时 | 失败降级 |
| :--- | :--- | :--- | :--- |
| poi.search | 按分类/标签/楼层/营业状态/关键词检索 POI | 1500ms | 返回空 + 提示换个说法 |
| poi.detail | 查 POI 详情与营业时间 | 1000ms | 跳过详情 |
| facility.nearest | 查最近的设施（卫生间/电梯/母婴室/服务台/ATM/出入口） | 1500ms | 返回楼层平面图入口 |
| route.plan | 规划跨楼层路线 | 2000ms | 返回文字方向指引（"F3 东侧，影院旁"） |
| promotion.list | 查 POI 或全场当前活动与优惠 | 1500ms | 不带优惠继续回答 |
| coupon.claim | 领取优惠券 | 2000ms | 提示稍后重试，不重复扣库存 |
| knowledge.query | 检索场地知识（RAG） | 2500ms | 降级为关键词 LIKE 检索，标记 degraded |
| recommend.rank | 对候选 POI 打分排序 | 1000ms | 按距离升序兜底 |

**工具调用循环约束**：单轮最多 6 次工具调用、总耗时上限 12s，超限立即用已有结果生成回答并标记 `degraded`；同一工具同一入参在一轮内不得重复调用（做入参指纹去重）；工具异常不抛出到用户，转为 `error_code` 记录并继续。

### 8.3 RAG 流程与幻觉控制（M6）

流程：文档入库 → 切片（目标 300—500 token，重叠 50）→ 向量化 → 存 `knowledge_chunks`；查询时 `venue_id` 过滤 + 向量检索 Top20 → 重排取 Top5 → 相关度低于阈值（默认 0.35，可配置）的片段丢弃 → 拼入 prompt 并强制要求"只依据提供的资料回答，资料中没有的信息必须说明没有"。

**幻觉控制三条硬规则**：
1. 回答中出现的店名、楼层、优惠必须来自工具结果或检索片段，模型不得自行生成具体店名（prompt 明确约束 + 后置校验：抽取回答中的 POI 名称与本轮工具结果比对，不匹配则记 warning 并降级为列表卡片回答）。
2. 无相关片段时固定回答"我暂时没有这方面的信息，你可以问问商场服务台"，同时给出服务台位置路线。
3. 所有回答附引用（`event: citations`），前端可查看出处。

**评测集**：20 条问句（见附录 B），每次改动 prompt 或工具后必须重跑，通过率与失败原因记录到 `packages/knowledge-rag/README.md`。

### 8.4 推荐打分（M7）

`score = Σ (factor_score_i × weight_i)`，8 因子与默认权重（全部可配置，写入 `recommend_weights` 或配置文件）：

| 因子 | 归一化方式 | 默认权重 |
| :--- | :--- | :--- |
| 距离 | `1 - min(distance/1000, 1)` | 0.22 |
| 楼层差 | `1 - min(floor_diff/5, 1)` | 0.10 |
| 营业状态 | 营业中 1.0；即将打烊 0.4；休息 0（直接过滤） | 0.15 |
| 当前优惠 | 有优惠 1.0，无 0 | 0.15 |
| 商户推荐权重 | `poi.recommend_weight` 归一化 | 0.10 |
| 热度 | `hot_score` min-max 归一化 | 0.10 |
| 目标类型匹配 | 意图标签与 POI tags 的匹配度 | 0.13 |
| 位置便利度 | 是否在当前动线/中庭附近 | 0.05 |

每个结果必须输出 `reasons[]`（人类可读，最多 3 条），打分明细写 `recommend_logs.factors`。候选为空返回空列表，不报错。

### 8.5 Agent 输出协议（含冻结能力预留）

```json
{
  "text": "……",
  "cards": [{"type": "poi_list|route|coupon|floor_map", "data": {}}],
  "citations": [{"document_id": 9, "snippet": "……"}],
  "voice_channel": null,     // A1 接入后填 {"audio_url": "...", "duration_ms": 3200}
  "avatar_channel": null,    // A2 接入后填 {"render_command": "...", "emotion": "friendly"}
  "degraded": false,
  "trace_id": "tr_x1"
}
```

---

## 9. 前端页面清单与状态要求

| 端 | 页面 | 必备状态 |
| :--- | :--- | :--- |
| M10 后台 | 登录、场地列表、楼层与地图管理、点位标注、POI 列表与编辑、活动管理、优惠管理、知识内容管理、推荐权重、设备列表、数据看板、账号与角色 | 加载态、空态、失败重试、表单校验错误、无权限提示、保存成功/失败 toast |
| M11 大屏 | 首页（欢迎语 + 快捷入口）、问答页（流式输出）、结果卡片页、路线展示页、二维码接力弹窗、闲置轮播广告、无障碍模式 | AI 思考中动画、超时兜底页、服务不可用静态信息页、无网络提示 |
| M12 手机 | 扫码落地页（接力路线）、路线详情、搜索页、问答页、POI 详情、优惠列表 | 首屏骨架屏、参数缺失错误页、弱网重试、微信内兼容 |

**状态设计要求**：每个数据请求的加载中/失败/超时/空数据/无权限五种状态都必须有明确 UI，禁止白屏与"卡在 loading"。

---

## 10. 异常路径与降级（生产必备）

| 场景 | 用户看到什么 | 系统行为 | 错误码 |
| :--- | :--- | :--- | :--- |
| AI 模型超时（>12s） | "我先帮你按关键词找了这些" + POI 列表卡片 | 降级为关键词检索，trace 标记 degraded | 3004 |
| AI 服务完全不可用 | 兜底话术 + 楼层平面图入口 + 服务台位置 | 熔断 60s，期间直接走关键词检索，不再打模型 | 3001 |
| 无相关知识 | "我暂时没有这方面的信息，可以问问服务台" + 服务台路线 | 记录 fallback 事件用于优化知识库 | 3003 |
| 路径不可达（如跨楼栋） | "这两个地点暂时无法规划步行路线" + 显示两点所在楼层平面 | 返回明确错误，不返回 500 | 2003 |
| 路网未构建/重建中 | 楼层平面图 + 文字方向指引 | 后台提示重建 | 2004 |
| 数据库只读/连接失败 | 静态信息页（营业时间、服务台电话、楼层索引） | 健康检查失败触发告警；前端读缓存 | 9001 |
| 重复提交表单 | "已提交，无需重复操作" | 幂等键命中返回首次结果 | 200（幂等） |
| 优惠券已领完 | "这张券已经领完了" + 推荐其他优惠 | 库存扣减用数据库原子操作，禁止先查后写 | 4002 |
| 登录连续失败 5 次 | "账号已锁定，请 15 分钟后再试" | 写 `locked_until`，记 operation_logs | 1002 |
| 越权访问 | "你没有该操作的权限" | 返回 403，记 operation_logs 与告警 | 1003 |
| 二维码过期（>30 分钟） | "路线已过期，请在大屏重新查询" + 场地首页入口 | 路线缓存 TTL 到期 | 2005 |
| 限流 | "访问太频繁，请稍后再试" | 返回 429 + Retry-After | 9002 |

---

## 11. 并发与容量测算

### 11.1 测算方法（假设值需按实际场地校准）

> ⚠️ 以下输入值为**我设定的假设场景**，用于确定架构量级，不是实测数据；接真实场地时必须重新采集。

公式：`峰值 QPS ≈ (大屏数 × 每屏每分钟交互次数 + 手机端并发用户 × 每用户每分钟请求数) ÷ 60 × 峰值系数`

| 场景 | 输入假设 | 计算 | 结果 |
| :--- | :--- | :--- | :--- |
| 单商场平日 | 10 屏 × 1 次/分 + 30 手机用户 × 1 次/分；峰值系数 3 | (10+30)/60×3 | ≈ 2 QPS |
| 单商场节假日 | 10 屏 × 2 次/分 + 120 手机用户 × 1.5 次/分；峰值系数 3 | (20+180)/60×3 | ≈ 10 QPS |
| 100 场地平台级 | 单场地节假日 × 100，但场地间时段错开，取同时系数 0.3 | 10×100×0.3 | ≈ 300 QPS |

### 11.2 结论：瓶颈不在 QPS，在长耗时 AI 请求

10 QPS 对任何 Web 框架都不构成压力，**真正的瓶颈是单次 AI 问答 3—12 秒的长连接**。因此架构必须做到：

1. **流式输出（SSE）**，首字 < 2s，避免用户等待感知与网关超时。
2. **AI 请求与常规请求隔离**：Agent 服务独立进程/独立连接池，防止长请求占满 worker 拖垮后台接口。
3. **并发会话上限 + 排队**：单实例并发 AI 会话上限可配置（默认 20），超限返回"当前咨询人数较多"并降级为关键词检索。
4. **超时分级**：工具级（1—2.5s）、模型级（12s）、端到端（15s），每级独立可配置。
5. **路线结果缓存**：`route_id` 缓存 30 分钟，手机接力不重复计算。
6. **埋点异步批量**：客户端本地攒批（≤50 条或 5s），服务端异步入库，绝不阻塞主链路。

### 11.3 容量估算（demo 数据规模）

单场地：POI 80、路网节点约 400、边约 900、知识文档 100（切片 500）、日问答 500 → 单日 events 约 5000 条、agent_traces 约 3000 条。年数据量在百万行级，PostgreSQL 单实例足够，无需分库分表；events 与 agent_traces 按月分区（生产阶段启用）。

---

## 12. 安全设计

| 项 | 具体实现 |
| :--- | :--- |
| 传输 | 全站 HTTPS（TLS 1.2+），HTTP 强制 301 跳转；Nginx 关闭 server_tokens |
| 密码 | bcrypt cost ≥12；密码强度校验（≥8 位含字母数字）；连续失败 5 次锁定 15 分钟 |
| 令牌 | JWT，access 有效期 2h、refresh 7d；密钥从环境变量注入；登出加黑名单（Redis 或数据库表） |
| SQL 注入 | 全部使用 ORM 参数化查询，禁止字符串拼接 SQL；CI 加静态扫描 |
| XSS | 前端输出统一转义；富文本（POI 介绍）用白名单过滤器；响应头 `Content-Security-Policy`、`X-Content-Type-Options: nosniff` |
| CSRF | 后台写操作校验 `Origin` + 双提交 token |
| 文件上传 | 白名单扩展名（jpg/png/webp/svg）+ MIME 校验 + 大小上限 5MB + 重命名为随机串存储；**SVG 必须做脚本剥离**（SVG 可内嵌 JS，是真实攻击面） |
| 权限 | 服务层强制注入租户/场地/商户过滤；越权用例全部写成自动化测试（见 2.3） |
| 幂等 | 写接口支持 `Idempotency-Key`；优惠券领取用唯一键 `coupon_id + anonymous_id` |
| 库存 | 优惠券扣减用 `UPDATE ... WHERE claimed_qty < total_qty` 原子操作，禁止先查后写 |
| 日志脱敏 | 手机号中间四位掩码、密码与 token 不落日志、AI prompt 中的用户输入按长度截断记录 |
| 密钥管理 | `.env` 不入库（`.gitignore`），仓库提供 `.env.example`；生产用密钥管理服务或部署时注入 |
| 依赖安全 | 锁定版本号；CI 跑依赖漏洞扫描 |

---

## 13. 容灾与兜底（三层）

**第一层 技术降级**：AI 不可用 → 关键词检索；路径不可算 → 楼层平面 + 文字指引；看板查询超时 → 返回上一次日聚合缓存；底图加载失败 → 显示 POI 列表模式。所有降级路径必须在开发阶段就实现并测试，不允许"上线后再补"。

**第二层 自动恢复**：AI 熔断 60s 后半开探测；数据库连接池自动重连；服务健康检查失败由容器编排重启；关键任务（路网重建、知识索引）失败可重跑且幂等。

**第三层 人工应急**：大屏兜底页固定展示服务台位置与电话；后台提供"AI 问答开关"（一键关闭 AI，全场降级为搜索+目录模式）；运营人员手册写明"系统不可用时怎么引导顾客"。

**故障影响矩阵**：

| 故障 | 影响范围 | RTO | RPO |
| :--- | :--- | :--- | :--- |
| AI 服务不可用 | 问答降级，导航与目录正常 | 60s 内自动降级 | 0 |
| 数据库故障 | 全站不可用，静态兜底页 | 目标 30 分钟 | ≤5 分钟（WAL 归档 + 每日全备） |
| 对象存储故障 | 底图与图片不可用，文字功能正常 | 1 小时 | 0 |
| 单模块服务崩溃 | 该模块功能不可用，其余正常 | 容器自动重启 < 30s | 0 |

---

## 14. 第三方依赖与成本

### 14.1 依赖清单（版本需锁定）

| 类别 | 选型 | 说明 |
| :--- | :--- | :--- |
| 后端框架 | FastAPI + Uvicorn | 异步、OpenAPI 自动生成 |
| ORM 与迁移 | SQLAlchemy 2.x（async）+ Alembic | 禁止 lazy loading，关联查询显式声明 |
| 数据库 | PostgreSQL 16 + pgvector | V1 不启用 PostGIS：室内用 SVG 平面坐标 x/y 与自算距离；V2 需地理坐标时再启用 |
| 缓存与队列 | Redis 7 | 路线缓存、限流、事件队列、熔断状态 |
| 前端 | React + TypeScript + Vite + pnpm workspace + Tailwind + TanStack Query + shadcn/ui | 三端共享组件包；不引入 Refine/React Admin 等后台框架 |
| 地图 | 自绘分层 SVG | 不使用商业室内地图 SDK（成本与授权风险） |
| 图算法 | networkx（A*/Dijkstra） | 成熟、易替换 |
| Agent 编排 | LangGraph（MIT） | **V1 唯一引入的 AI 框架**：有状态图 + 检查点持久化，避免自研编排循环 |
| 检索与索引 | 自建 RAG 管道 + pgvector | 切片/检索/重排/引用/幻觉后置校验自建，约 200 行；不引入 LlamaIndex（减少一层人类无法验收的抽象，且自建版本是面试考点） |
| 模型供应商抽象 | 自建 `LLMProvider` 类 + OpenAI 兼容 SDK | 环境变量配置模型名、超时、重试、每日调用上限与超限降级；不引入 LiteLLM（V1 单供应商，不需要多 Key 轮询） |
| Agent 可观测 | 自建 `agent_traces` 表 + 查询接口 + 前端时间线 | PRD 已要求 trace 落库，自建即可满足作品集演示；不引入 Langfuse（少一个外部服务与学习成本） |
| 大模型 | 通过自建 Provider 抽象接入 | ⚠️ 具体模型与单价需自行询价 |
| 室内地图与寻路（复用候选） | KnotzerIO/indoor-wayfinder、openindoormaps、Navigine 寻路库 | 开工前由 CC 核验 license 与维护状态，结论写入 REUSE.md |

**V1 明确不引入清单**：LlamaIndex、LiteLLM、Langfuse、RAGFlow、Dify、PostGIS、Refine、React Admin、Celery（异步任务用 FastAPI BackgroundTasks 或 Redis 队列自建）、Kubernetes。选型原则是"最小陌生面"：人类负责人只熟悉 LangGraph，每多引入一个陌生框架就多一处无法验收、面试讲不清的黑盒。将来确需引入，必须说明理由、登记 `REUSE.md`，并封装在所属模块内部，禁止把第三方类型泄漏成跨模块接口。
| 语音/数字人 | 冻结 | ⚠️ V2 接入前需询价与合规评估 |
| 容器与部署 | Docker + docker compose + Nginx | V1 不上 K8s |

**第三方风险盘点**：AI API 需确认配额上限、限流规则、新账号冷启动限制、单价与计费口径；对象存储需确认流量费用；短信（若 V2 用）需确认签名审核周期。任何第三方都必须有超时、重试与降级，禁止假设"永远可用"。

### 14.2 成本估算

| 项 | 金额 | 口径说明 |
| :--- | :--- | :--- |
| 云服务器（demo） | 500—1500 元/年（基础型）；生产建议 1500—3000 元/年（商城型）；高并发 5000 元以上/年 | 行业报价文章口径，实际按所选厂商询价 |
| 域名 + SSL | 50—200 元/年 | 同上口径 |
| 微信小程序认证（若做小程序端） | 企业 300 元/年，个体工商户 30 元/年 | 2026 年行业口径 |
| 对象存储与流量 | ⚠️ 需按用量询价 | 底图与图片存储 |
| 短信（V1 不用） | 0.03—0.1 元/条 | 行业口径 |
| 微信支付手续费 | V1 无支付，故为 0 | 官方标准 0.6% |
| 大模型调用 | ⚠️ 必须自行询价，用公式预估：`月成本 ≈ 日问答次数 × 单次平均 token（输入+输出）× 单价 × 30` | 例：日 500 次问答，单次 4000 token，按你所选模型单价代入 |
| 数字人/TTS/ASR 授权 | ⚠️ 冻结，V2 询价 | — |
| 年度维护（若对外报价） | 开发总价的 10%—20%/年 | 行业惯例口径 |

**成本控制硬要求**：Provider 抽象层必须支持每日调用次数上限与超限自动降级；`agent_messages` 记录 `tokens_in/tokens_out`，后台可按天统计 token 消耗，这是你控制成本的唯一依据。

---

## 15. 埋点事件字典与指标定义

| event_type | 触发时机 | 关键 payload | 对应指标 |
| :--- | :--- | :--- | :--- |
| ai_query | 每次 AI 问答完成 | intent、latency_ms、degraded、tool_count | AI 咨询次数 |
| ai_query_failed | 问答失败或降级 | error_code | 失败率 |
| search | 用户主动搜索 | keyword、result_count、floor_id | 用户搜索内容、店铺搜索排行 |
| poi_view | 查看 POI 详情 | poi_id、source（ai/search/list） | 热门目的地 |
| poi_recommended | POI 出现在推荐结果中 | poi_id、rank、score | 商铺被推荐次数 |
| route_plan | 路线规划成功 | route_id、from_floor、to_floor、distance_meter | 导航次数 |
| route_handover | 扫码接力成功 | session_id、route_id | 接力转化率 |
| coupon_claim | 领券成功 | coupon_id、poi_id | 优惠券领取次数 |
| coupon_use | 核销（V1 仅记录） | coupon_id | 优惠券核销次数 |
| device_active | 设备心跳 | device_id、status | 导视设备使用次数 |
| ad_impression / ad_click | 广告曝光与点击 | ad_id | 广告效果 |

**11 项指标定义**（`metric_code`）：`ai_query_count`、`search_keyword_top`、`poi_search_rank`、`route_plan_count`、`hot_destination_top`、`poi_recommend_count`、`coupon_claim_count`、`coupon_use_count`、`device_usage_count`、`traffic_by_hour`、`handover_rate`。全部支持按 `venue/floor/device/poi/hour` 维度聚合。

---

## 16. 部署方案（M13）

```
deploy/
├── docker/            # 每个服务一个 Dockerfile（多阶段构建，非 root 用户）
├── nginx/             # 反向代理 + HTTPS + 静态资源 + SSE 关闭缓冲（proxy_buffering off）
├── migrations/        # Alembic，唯一改表入口
├── seed/              # 虚拟商场 demo 数据（3 层、60—80 POI、20 设施、10 活动优惠、100 篇知识）
└── scripts/           # deploy.sh / backup.sh / healthcheck.sh / rollback.sh
```

服务清单：`postgres`、`redis`、`content-service`、`route-service`（M2+M3）、`agent-service`（M5+M6+M7）、`analytics-service`、`admin-web`、`screen-web`、`mobile-h5`、`nginx`。

要求：
1. `docker compose up -d` 一条命令起全套；`docker compose -f docker-compose.demo.yml up -d` 起 demo。
2. 服务间用服务名连接，**禁止 localhost**。
3. 三套环境配置分离（`.env.dev` / `.env.demo` / `.env.prod`），变量名一致、值不同。
4. 每个服务提供 `GET /health`（存活）与 `GET /ready`（依赖就绪），compose 配 healthcheck。
5. 部署脚本流程：拉镜像 → 跑迁移（幂等）→ 起服务 → 健康检查 → 灌 seed（仅 demo）→ 输出访问地址。
6. 备份：每日 `pg_dump` 定时任务，保留 14 天，备份文件校验可恢复（每月演练一次）。
7. 回滚：保留上一版镜像 tag，`rollback.sh` 一条命令回退（迁移必须向后兼容）。
8. CI：lint（含跨包 import 检查）→ 单元测试 → 构建镜像 → e2e 冒烟（顾客问路全链路）。

---

## 17. 测试策略与验收标准

| 层级 | 范围 | 通过标准 |
| :--- | :--- | :--- |
| 单元测试 | M3 路径规划、M5 意图解析与工具循环、M6 检索、M7 打分、M8 状态机与幂等 | M3/M5/M7 覆盖率 ≥70%，打分逻辑 ≥80% |
| 接口测试 | 全部 P0 接口 | 正常 + 异常 + 越权三类用例齐全 |
| 契约测试 | 各服务响应是否符合 M0 Schema | 全部通过 |
| e2e | 顾客问路全链路、扫码接力、后台改数据后 AI 感知 | 3 条主流程全绿 |
| AI 评测 | 附录 B 的 20 条问句 | 通过率 ≥80%，失败原因归档；RAG Top3 命中率有量化数字 |
| 性能 | 路径规划、问答首字、后台列表 | 达到第 5 节指标 |
| 降级演练 | 手动杀掉 AI 服务与数据库 | 兜底 UI 正常，无白屏，无 500 泄漏堆栈 |

**模块完成定义（三选一不算完成，必须全满足）**：能独立跑通示例 + 测试通过 + README 达标（含"如何摘出复用"一节）。

---

## 18. 用户故事与任务分解（按依赖排序）

> 执行顺序严格自上而下：契约 → 数据库 → 内核 → AI → 服务 → 端 → 部署 → 文档。

| ID | 标题 | 描述 | 验收标准 | 优先级 |
| :--- | :--- | :--- | :--- | :--- |
| US-001 | 仓库脚手架与 CI | 作为开发者，我需要 monorepo 骨架、lint 与 CI | pnpm/uv workspace 可用；跨包 import 检查生效；CI 跑通空测试 | 1 |
| US-002 | M0 契约定稿 | 统一响应体、错误码、事件 schema、OpenAPI 骨架 | `make validate` 与 `make gen` 通过；DECISIONS.md 记录冻结 | 2 |
| US-003 | M1 多租户与鉴权 | 租户上下文、四角色 RBAC、配置加载、结构化日志、trace_id | 跨租户隔离测试通过；越权返回 1003；日志含 trace_id | 3 |
| US-004 | 数据库迁移基线 | Alembic 初始化 + 第 6 节全部 DDL | 迁移可重复执行；空库一键建表；类型检查通过 | 4 |
| US-005 | M2 空间模型与数据字典 | Venue/Floor/POI/分类字典 + 复合查询 | seed 虚拟商场成功；按分类/楼层/营业状态/标签查询有测试 | 5 |
| US-006 | M4 地图渲染与 PoiPicker | 分层 SVG、缩放拖动、楼层切换、点位标注 | 独立 demo 可交互；PoiPicker 输出坐标并回写 | 6 |
| US-007 | M3 路网与路径规划 | 图构建、A*、跨层边、无障碍、距离耗时 | 跨 3 层路线正确；无障碍剔除楼梯；不可达返回 2003；覆盖率 ≥70% | 7 |
| US-008 | M6 知识入库与检索 | 切片、向量化、检索、出处、阈值过滤 | 20 问评测集 Top3 命中率有数字；无依据时返回空 | 8 |
| US-009 | M5 Agent 编排 | 意图解析、工具注册、调用循环、trace、SSE 流式 | 20 条问句通过率 ≥80%；trace 接口可查完整链路；类型检查通过 | 9 |
| US-010 | M5 降级与熔断 | 模型超时/不可用降级、并发上限、限流 | 杀掉模型服务后返回兜底且不 500；熔断 60s 生效 | 10 |
| US-011 | M7 推荐打分 | 8 因子打分 + 理由 + 日志 | 改权重能改排序（有测试）；覆盖率 ≥80% | 11 |
| US-012 | M8 内容服务 | POI/活动/优惠/知识 CRUD + 状态机 + 幂等 | 状态机流转测试；领券幂等；商户只能改自己数据 | 12 |
| US-013 | M10 运营后台 | 登录、内容与地图维护、账号、看板入口 | 改营业时间后 AI 回答变化（e2e）；五种状态 UI 齐全 | 13 |
| US-014 | M12 手机 H5 | 扫码接力、路线、搜索、问答轻版 | 扫码参数解析正确；路线与大屏一致；微信内可用 | 14 |
| US-015 | M11 大屏 | 全屏触屏 UI、流式问答、路线、二维码、闲置轮播 | 1080p 与 4K 适配；超时兜底页正常 | 15 |
| US-016 | A1/A2 冻结接口 | 语音与数字人适配器接口 + 空实现 | 返回 5001/5002；mock 实现接入时不改 M5 与端层（有测试） | 16 |
| US-017 | M9 埋点与看板 | 事件上报、幂等、11 项指标、6 项看板可视化 | 指标数值可与明细核对；重复上报不重复计数 | 17 |
| US-018 | M13 部署 | 容器化、三环境、健康检查、备份、一键部署 | 干净服务器一条命令部署成功；备份可恢复 | 18 |
| US-019 | e2e 与降级演练 | 三条主流程 + 故障演练 | 全绿；无白屏无堆栈泄漏 | 19 |
| US-020 | 作品集材料 | 架构图、3 篇难点解析、每模块 README、演示视频、发布 | 公网 demo 可访问；视频 ≤2 分钟；GitHub 与程序员客栈已发布 | 20 |

---

## 19. V2 规划（冻结项，写入 README 展示规划能力）

1. 语音全链路：麦克风阵列 + 唤醒 + ASR + TTS，噪声环境识别率验收标准
2. 数字人：形象授权、口型驱动、渲染通道
3. 设备 OTA：远程更新、灰度、失败回滚、异常报警
4. 手机实时室内定位：蓝牙/UWB 信标部署与蓝点导航
5. 个性化推荐：用户画像与协同过滤
6. 多语言与国际化
7. 商户独立后台与优惠券核销闭环
8. 支付与交易、发票
9. 开放 API 与第三方接入、跨租户运营看板
10. 多场景扩展包：医院、景区、校园、园区、政务大厅（只换数据字典与 prompt 模板）

---

## 20. 上线检查清单（demo 转生产时逐项过）

**技术项**：HTTPS 证书有效且自动续期 · 所有服务健康检查通过 · 数据库迁移在生产库演练过 · 备份任务已配置且验证可恢复 · 回滚脚本演练过 · 密钥全部从环境注入且未入库 · 依赖漏洞扫描通过 · 限流与熔断阈值已按真实流量调整 · 日志脱敏生效 · 慢查询已优化

**功能项**：三条主流程 e2e 全绿 · 五种前端状态（加载/失败/超时/空/无权限）全覆盖 · 越权测试全部通过 · AI 降级演练通过 · 埋点数据与业务数据可互相核对

**第三方预热**：AI 模型账号已实名与充值、配额与限流规则已确认、并发上限已申请调整 · 对象存储与域名备案完成 · 若用短信，签名与模板审核已通过（审核周期需预留）

**发布策略**：先在 1 个场地灰度 → 观察 3 天核心指标（问答成功率、AI 超时率、路线规划失败率）→ 再扩场地

**上线后 Smoke Test**：问路一次 · 推荐一次 · 领券一次 · 扫码接力一次 · 后台改一条数据并验证 AI 感知 · 看板出数 · 设备心跳正常

**快速回滚触发条件**：问答成功率 < 80% 持续 30 分钟 · 数据库连接失败率 > 5% · 任一核心接口错误率 > 10% · 出现越权数据泄漏（立即回滚并排查）

**人工应急预案**：AI 全挂 → 后台一键关闭 AI 问答，大屏切目录模式，现场引导至服务台；数据库挂 → 大屏切静态信息页，运营人员口头引导；单设备故障 → 后台标记维护并现场张贴指引

---

## 附录 A：2 分钟演示视频脚本

| 时间 | 画面 | 旁白要点 |
| :--- | :--- | :--- |
| 0:00—0:15 | 大屏首页 + 一句话标题 | "一套可复制到任意场地的 AI 空间导视平台：自然语言问答 + 室内跨楼层导航 + 商业运营后台" |
| 0:15—0:35 | 顾客在大屏输入"有没有适合情侣吃饭的地方，最好有优惠" | 展示流式输出与推荐卡片，特写"距你 180 米 / 营业中 / 满 100 减 20"三条理由 |
| 0:35—0:55 | 点击路线 → 跨楼层路线动画 → 扫码 → 手机接力 | 强调跨楼层（扶梯段）与手机接力是同一条路线 |
| 0:55—1:15 | 切到 trace 页面 | 展示这一次问答的完整工具调用链：意图解析 → poi.search → promotion.list → recommend.rank → route.plan，这是 Agent 编排能力的证明 |
| 1:15—1:40 | 运营后台改一家店营业时间为"休息中" → 回大屏再问一次 | 结果不再推荐该店，证明数据实时生效与多租户内容治理 |
| 1:40—1:55 | 数据看板 | 11 项指标中的 6 项，说明可用于商场经营决策 |
| 1:55—2:00 | 架构图 + 模块列表 | "14 个模块，每个可独立运行与单独复用；换场景只需替换数据字典与 prompt" |

---

## 附录 B：Agent 评测问句（20 条，改动后必须重跑）

1. 卫生间在哪里
2. 最近的母婴室在哪
3. 我想吃火锅
4. 有没有适合情侣吃饭的地方
5. 今天有什么优惠
6. 带我去电影院
7. 商场几点关门
8. 哪里有卖衣服的
9. 有免费的 Wi-Fi 吗
10. 从这里到停车场怎么走
11. 有电梯吗，我推婴儿车
12. 三楼有什么吃的
13. 有没有便宜的午餐
14. 服务台在哪
15. 这家店现在营业吗（指向前一条结果）
16. 帮我领那张满 100 减 20 的券
17. 附近有什么咖啡店
18. 超市在几楼
19. 今天天气怎么样（应触发兜底：不编造，说明无此信息）
20. 你们商场有多少家店（应走 knowledge.query，答案需有出处）

**评测记录格式**：`问句 | 期望意图 | 实际意图 | 工具链 | 是否命中正确 POI | 是否有幻觉 | 耗时 | 结论`，写入 `packages/agent-orchestrator/EVAL.md`。

---

## 附录 C：数据与合规提醒

1. demo 数据的商场名称、店铺、优惠**全部虚构**，可参考真实业态结构，不得使用真实商场名称、真实商户名单与真实促销信息。
2. 顾客侧仅采集 `anonymous_id` 与行为事件，不采集姓名、手机号；若 V2 引入会员体系，需补充个人信息处理告知与同意机制。
3. 埋点数据保留期见第 5 节；日志与 trace 中的用户输入需截断与脱敏。

---

内容由 AI 生成
