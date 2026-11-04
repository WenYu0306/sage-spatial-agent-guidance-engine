# 空间智能体导视平台 · 架构设计与模块契约 v1

> 本文档是项目的**架构宪法**。开发过程中任何与本文档冲突的实现，以本文档为准；确需变更时，必须先修改本文档并在 `DECISIONS.md` 记录一行原因。
>
> 配套文档：`空间智能体导视平台-PRD-v1.md`（功能规格、数据模型 DDL、API 定义、验收标准）。两份文档一起作为 Claude Code 的项目上下文。

---

## 0. 怎么把这两份文档喂给 Claude Code

1. 在仓库根目录建 `CLAUDE.md`，内容见本文档第 11 节，指向这两份文档。
2. 每次开新会话，先让 Claude Code 读 `CLAUDE.md` + 本文档 + PRD 中**当前模块对应章节**，不要一次全塞（上下文过长会导致它忽略细节）。
3. 一次任务只做一个模块的一个子任务，改动控制在 200—400 行。
4. 每个任务的标准指令模板：

```
你是本项目的开发者。请先读 CLAUDE.md、ARCHITECTURE.md 第 6 节 M<编号> 模块契约、PRD 第 <X> 节。
本次任务：<一句话任务>
约束：
- 只能修改 packages/<module>/ 下的文件，禁止跨包 import 其他模块内部实现
- 遵循 ARCHITECTURE.md 第 8 节统一契约（响应体、错误码、trace_id）
- 配置项全部从环境变量读取，禁止硬编码
- 同时编写测试，测试必须能独立运行（不依赖其他模块真实服务，用 mock）
- 完成后运行该模块的独立启动脚本与测试，把结果贴给我
先输出实现方案（不超过 15 行），等我确认后再写代码。
```

最后一条"先输出方案等确认"是硬要求，它能挡掉大部分返工。

---

## 1. 项目定位

**一句话**：一套场景无关的空间智能体内核（多租户 + 空间数据 + 路径规划 + Agent 编排 + RAG + 推荐），首个验证场景为商场 AI 导视。

**三个目标（按优先级）**：

| 目标 | 衡量标准 |
| :--- | :--- |
| 作品集资产 | 有公网可访问 demo、2 分钟演示视频、架构图、3 篇难点解析、每个模块独立 README |
| 可复用组件 | 每个 P0 模块能单独 `cd` 进去一条命令跑起来并跑通示例；换场景只改配置与数据字典 |
| 可升级为生产 | 第 9 节 7 个开关全部打开；PRD 中异常路径、降级、安全、部署章节全部落地 |

**非目标（明确不做）**：真实商场数据接入、支付、真实设备 OTA、数字人、多语言、移动端原生 App。

---

## 2. 范围冻结

### 2.1 P0 必做（11 个模块）

M0 api-contract、M1 platform-core、M2 spatial-model、M3 route-engine、M4 map-render、M5 agent-orchestrator、M6 knowledge-rag、M8 content-service、M10 admin-web、M12 mobile-h5、M13 deploy

### 2.2 P1 争取（3 个模块）

M7 recommender、M9 analytics-service、M11 screen-web

> M11 大屏与 M12 手机 H5 共享组件，边际成本低，且演示视频观感最强，建议做。若时间不足，先砍 M9 的看板可视化（保留埋点入库），再砍 M7 的个性化权重（保留固定权重打分）。

### 2.3 冻结但预留接口（2 个适配器）

| 编号 | 名称 | 冻结范围 | 预留方式 |
| :--- | :--- | :--- | :--- |
| A1 | voice-adapter | 不实现 ASR/TTS 真实接入 | 定义 `VoiceAdapter` 接口（`transcribe()` / `synthesize()`）+ 空实现返回"未启用"；M5 输出协议预留 `voice_channel` 字段；M11/M12 预留语音入口按钮（灰态） |
| A2 | avatar-adapter | 不实现数字人 | 定义 `AvatarAdapter` 接口（`render_speech()` / `idle()`）+ 空实现；M5 输出协议预留 `avatar_channel` 字段；大屏 UI 预留数字人容器位 |

**预留的正确标准**：将来接真实语音/数字人时，只新增适配器实现 + 改配置，**不修改 M5 编排层和端层业务代码**。这条写进 A1/A2 的验收标准。

### 2.4 明确砍掉（写入 README 的 V2 规划，不进代码）

摄像头人体检测与靠近唤醒、手势交互、数字人口型同步、多语言、个性化推荐（协同过滤）、设备 OTA 远程更新/重启、商户独立后台（用运营后台的商户视图代替）、优惠券核销完整闭环（只做领取与状态记录）、手机实时室内定位蓝点、多商场同时在线运营（架构支持，demo 只演示 1 家 + 后台可切换第 2 家空数据）。

---

## 3. 总体架构

```
┌─────────────────────────────────────────────────────────────┐
│  L4 端层                                                     │
│  M10 admin-web      M11 screen-web      M12 mobile-h5        │
│  （运营后台）        （大屏触屏）         （扫码接力）          │
└──────────────┬──────────────┬──────────────┬────────────────┘
               │  HTTP / SSE（统一契约 M0）    │
┌──────────────▼──────────────▼──────────────▼────────────────┐
│  L3 业务服务层                                                │
│  M8 content-service          M9 analytics-service            │
│  （POI/活动/优惠/知识 CRUD）   （埋点入库/指标聚合）            │
└──────────────┬─────────────────────────────┬────────────────┘
               │                             │
┌──────────────▼─────────────────────────────▼────────────────┐
│  L2 AI 能力层                                                 │
│  M5 agent-orchestrator  ←→  M6 knowledge-rag                 │
│         ↕ 工具调用                  ↕ 检索                    │
│  M7 recommender      [A1 voice-adapter]  [A2 avatar-adapter] │
└──────────────┬──────────────────────────────────────────────┘
               │ 工具调用（POI查询 / 路径规划 / 优惠查询）
┌──────────────▼──────────────────────────────────────────────┐
│  L1 空间智能内核（复用价值最高）                                │
│  M2 spatial-model  →  M3 route-engine  →  M4 map-render       │
└──────────────┬──────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────┐
│  L0 契约与基础层                                              │
│  M0 api-contract（OpenAPI/事件/错误码）                        │
│  M1 platform-core（多租户/RBAC/配置/日志+trace/事件总线/埋点SDK）│
│  M13 deploy（容器/环境/迁移/备份/健康检查）                     │
└─────────────────────────────────────────────────────────────┘
```

### 3.1 核心数据流：顾客在大屏问"有没有适合情侣吃饭的地方"

```
M11 大屏 → POST /api/v1/agent/chat（带 tenant_id、venue_id、device_id、session_id）
  → M5 agent-orchestrator
      1. 意图解析：{intent: "poi_recommend", cuisine: null, scene: "date", need_route: true}
      2. 工具调用 poi.search（→ M8/M2）：分类=餐厅、营业中、场景标签含"约会"
      3. 工具调用 promotion.list（→ M8）：查这些店当前优惠
      4. 调 M7 recommender：8 因子打分排序
      5. 调 M6 knowledge-rag：补充店铺特色描述，带引用
      6. 调 M3 route-engine：为 Top1 预算路线（起点=当前大屏位置）
      7. 生成回答 + 结构化卡片（店铺列表 / 路线 / 优惠 / 引用）
      8. 全程写 agent_traces（每一步工具名、入参、耗时、结果摘要）
  → 流式返回（SSE）给大屏；同时 M1 埋点 SDK 写 events
  → 顾客扫码 → M12 手机 H5 带 session_id + route_id 接力
```

### 3.2 架构原则（7 条，写代码时反复对照）

1. **契约先行**：所有跨模块通信只走 M0 定义的 HTTP/事件，禁止跨包 import 内部实现。
2. **租户贯穿**：任何数据表、任何查询、任何缓存 key 都带 `tenant_id`，无例外。
3. **内核无业务**：M2/M3/M5/M6/M7 不得出现"商场""店铺""优惠券"字样，业务语义只存在于 M8 与配置的数据字典中。这是复用的根本保障。
4. **配置外置**：模型名、prompt、打分权重、阈值、超时、重试次数全部从配置注入。
5. **可观测优先**：trace_id 从端层生成，贯穿 Agent 每一步工具调用，落库可查。
6. **降级可用**：AI 不可用 → 关键词检索；路径不可算 → 楼层平面 + 文字指引。任何单点故障不让整个产品白屏。
7. **可独立运行**：每个模块自带 mock 数据与示例脚本，能单独跑通。

---

## 4. 仓库结构

```
spatial-agent-platform/
├── CLAUDE.md                     # Claude Code 入口（第 11 节）
├── ARCHITECTURE.md               # 本文档
├── PRD.md                        # 配套 PRD
├── DECISIONS.md                  # 技术决策记录（每个决策一行）
├── docker-compose.yml            # 一键起全套（dev）
├── docker-compose.demo.yml       # demo 环境
├── .env.example                  # 所有配置项模板（不含真实密钥）
├── packages/
│   ├── api-contract/             # M0
│   │   ├── openapi/              # 各模块 yaml
│   │   ├── schemas/              # 统一响应体、事件、错误码
│   │   └── README.md
│   ├── platform-core/            # M1（Python 包）
│   ├── spatial-model/            # M2（Python 包）
│   ├── route-engine/             # M3（Python 包 + FastAPI 服务）
│   ├── map-render/               # M4（前端包，TS）
│   ├── agent-orchestrator/       # M5（Python 包 + FastAPI 服务）
│   ├── knowledge-rag/            # M6（Python 包 + FastAPI 服务）
│   ├── recommender/              # M7（Python 包）
│   ├── voice-adapter/            # A1（接口 + 空实现）
│   ├── avatar-adapter/           # A2（接口 + 空实现）
│   ├── content-service/          # M8（FastAPI 服务）
│   ├── analytics-service/        # M9（FastAPI 服务）
│   ├── admin-web/                # M10（前端应用）
│   ├── screen-web/               # M11（前端应用）
│   └── mobile-h5/                # M12（前端应用）
├── deploy/                       # M13
│   ├── docker/                   # 各服务 Dockerfile
│   ├── nginx/
│   ├── migrations/               # 数据库迁移（唯一改表入口）
│   ├── seed/                     # demo 数据脚本（虚拟商场）
│   └── scripts/                  # 一键部署、备份、健康检查
├── docs/
│   ├── 难点解析-01-跨楼层路径规划.md
│   ├── 难点解析-02-Agent工具编排与幻觉控制.md
│   ├── 难点解析-03-多租户与可复用内核的边界设计.md
│   └── demo-视频脚本.md
└── tests/
    └── e2e/                      # 跨模块端到端测试（顾客问路全链路）
```

### 4.1 工程约定（8 条，违反即视为未完成）

1. **每个模块目录必须包含**：`README.md`（做什么/接口/如何单独跑/示例/复用摘出方法）、`pyproject.toml` 或 `package.json`（独立依赖与版本号）、`tests/`、`examples/`（可运行示例脚本）、`Dockerfile`（服务端模块）。
2. **独立运行验收**：`cd packages/<module> && make demo`（或 `pnpm demo`）必须能在不启动其他模块的情况下跑通，依赖的外部模块用内置 mock。
3. **禁止跨包 import**：用 lint 规则强制（Python: `import-linter` 配置 contracts；TS: `eslint-plugin-boundaries`）。违规直接 CI 失败。
4. **契约变更流程**：改 M0 → 在 `DECISIONS.md` 记一行 → 同步改受影响模块 → 跑 e2e。禁止先改实现后补契约。
5. **测试要求**：M3 路径规划、M5 Agent 编排、M7 推荐打分必须有单元测试且覆盖率可量化（目标 ≥70%）；每个服务端模块必须有接口冒烟测试。
6. **数据库变更只走 migration**：`deploy/migrations/`，禁止手改表、禁止 ORM 自动建表上生产。
7. **提交规范**：`feat(M3): 支持跨楼层电梯边权重` / `fix(M5): 工具调用超时降级` / `docs: 更新契约`。
8. **配置零硬编码**：CI 加一条检查，扫描 `packages/` 下是否出现明文 API Key、模型名、租户 ID、prompt 字符串（prompt 放配置文件或数据库）。

---

## 5. 模块清单总览

| 编号 | 模块 | 层 | 类型 | 优先级 | 预估人天 | 复用半径 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| M0 | api-contract | L0 | 契约 | P0 | 3 | 所有项目 |
| M1 | platform-core | L0 | Python 包 | P0 | 6 | 任何多租户 SaaS |
| M2 | spatial-model | L1 | Python 包 | P0 | 6 | 医院/景区/校园/园区/展馆/仓库导视 |
| M3 | route-engine | L1 | 服务 | P0 | 10 | 同上 + 巡检路径、物流动线 |
| M4 | map-render | L1 | 前端包 | P0 | 8 | 任何室内地图产品 |
| M5 | agent-orchestrator | L2 | 服务 | P0 | 14 | 任何工具调用型 Agent |
| M6 | knowledge-rag | L2 | 服务 | P0 | 8 | 任何企业知识库问答 |
| M7 | recommender | L2 | Python 包 | P1 | 5 | 本地生活/内容推荐 |
| A1 | voice-adapter | L2 | 接口 | 冻结 | 1 | 语音类产品 |
| A2 | avatar-adapter | L2 | 接口 | 冻结 | 1 | 数字人产品 |
| M8 | content-service | L3 | 服务 | P0 | 8 | 任何内容运营后台 |
| M9 | analytics-service | L3 | 服务 | P1 | 5 | 任何行为分析 |
| M10 | admin-web | L4 | 前端应用 | P0 | 10 | 低（组件可复用） |
| M11 | screen-web | L4 | 前端应用 | P1 | 5 | 低（与 H5 共享组件） |
| M12 | mobile-h5 | L4 | 前端应用 | P0 | 6 | 低 |
| M13 | deploy | L5 | 工程 | P0 | 5 | 所有项目 |
| — | 作品集材料与视频 | — | 文档 | P0 | 8 | — |

**工作量口径（已按"CC 全开发"修正）**：上表人天是"人工独立开发"的参照量，用于判断模块相对轻重，不是你的排期依据。本项目由 Claude Code 承担全部编码，你的时间花在产品决策、方案审批、验收与理解代码上。因此真正的约束不是编码速度，而是三条：

1. **你的验收吞吐量**：CC 一天能产出你两天验不完的量。必须严格一次一个 US，验完再开下一个，否则 bug 会叠加到无法定位。
2. **不会等比压缩的部分**：开源选型调研、demo 数据录入与地图标注、部署联调、评测集调优、作品集材料与演示视频——这些占你实际时间的大头，估算时不要按"CC 写得快"打折。
3. **API 成本与限流**：Agent 模块开发期会高频调用模型，必须设每日调用上限并做降级。⚠️ 单价需按所选模型自行询价。

据此，12 周排期保持不变，但**进度红线的判断依据改为"已验收通过的 US 数量"，而不是"CC 写了多少代码"**。若第 6 周末 US-001 至 US-010 未全部验收通过，立即砍 M9 看板与 M7 个性化权重，保住 M3 路径引擎、M5 Agent 编排、M6 RAG 三个核心。


---

## 6. 模块契约（逐个）

> 每个模块的契约包含：职责、对外接口、依赖、独立运行方式、复用摘出方式、验收标准。接口路径与字段以 M0 的 OpenAPI 为准，此处为设计约定。

### M0 api-contract

- **职责**：定义所有跨模块通信的契约。统一响应体、错误码、分页、鉴权头、trace 头、事件 schema、OpenAPI 文件。
- **对外产出**：`schemas/common.yaml`、`openapi/<module>.yaml`、生成的 TS 类型与 Python Pydantic 模型（供各模块引用）。
- **依赖**：无（第一个做）。
- **独立运行**：`make validate` 校验所有 OpenAPI 文件合法且无冲突；`make gen` 生成客户端类型。
- **复用摘出**：整个目录复制即可，改 `info.title` 与服务地址。
- **验收标准**：统一响应体与错误码表定稿；所有 P0 模块的接口在 OpenAPI 中有定义；类型生成脚本可跑通；契约冻结宣告写入 DECISIONS.md。

### M1 platform-core

- **职责**：多租户上下文、RBAC 鉴权骨架、配置加载与校验、结构化日志（含 trace_id）、事件总线（进程内 + 可切 Redis）、埋点 SDK、统一异常处理。
- **对外接口**（Python 包导出）：`TenantContext`、`require_role()`、`Settings`、`get_logger()`、`event_bus.publish/subscribe`、`track()`、`AppError`。
- **依赖**：M0。
- **独立运行**：`examples/demo.py` 演示两个租户数据互不可见、角色鉴权拦截、事件发布订阅、日志带 trace_id。
- **复用摘出**：复制包 + 改 `Settings` 的默认配置项；角色枚举按项目改。
- **验收标准**：跨租户查询默认被拦截（有测试证明）；四种角色（平台/商场/商户/设备）鉴权可用；trace_id 能从请求头透传到日志与事件；配置缺失时启动即报错而非运行时崩。

### M2 spatial-model

> **实现形态（D-029，2026-11-05）**：空间数据的 CRUD 端点由 M8 承载（/pois/nearest、/route-nodes、/route-edges、/pois 场景参数），本包重定位为**纯空间计算库**（距离/最近排序/连通性纯函数，供 M3/M4/scene_check import）。理由与恢复条件见 DECISIONS.md D-029。

- **职责**：空间数据模型与查询。楼层、区域、POI、设施、地图图层、路网节点与边的数据定义与 CRUD；空间索引；数据字典（POI 分类体系可配置，这是换场景的关键）。
- **对外接口**：`Venue/Floor/POI/Facility/MapLayer/RouteNode/RouteEdge` 模型与仓储；`poi.query(filters)`、`poi.nearby(point, radius)`、`dict.list_categories(tenant_id)`。
- **依赖**：M0、M1。
- **独立运行**：`examples/load_demo_venue.py` 灌入一个虚拟商场（3 层、60—80 POI、20 设施）并跑若干查询。
- **复用摘出**：换 `seed/` 里的数据字典（把"店铺/餐厅/影院"换成"科室/诊室/检查室"）即可用于医院场景，代码不改。
- **验收标准**：数据字典可配置且有测试；POI 支持 8 项字段（名称/分类/楼层/位置/营业时间/介绍/图片/联系方式）；按分类、楼层、营业状态、标签的复合查询可用；跨租户隔离测试通过。

### M3 route-engine

- **职责**：路网图构建与路径规划。把每层可通行区域建为图，电梯/扶梯作为跨层边（带垂直耗时权重），支持无障碍过滤、距离与耗时估算、多点途经。
- **对外接口**：`POST /api/v1/route/plan`（起点、终点、途经点、无障碍偏好、租户/场地）→ 返回分段路线（每段：楼层、节点序列、距离、耗时、交通方式）+ 路线总览。`POST /api/v1/route/graph/rebuild`（后台维护地图后重建图）。
- **依赖**：M0、M1、M2。
- **独立运行**：`examples/plan_demo.py` 用内置 mock 路网算一条跨 3 层路线，打印分段结果与总耗时。
- **复用摘出**：医院（科室间路线 + 无障碍/轮椅）、景区（景点游览动线）、仓库（拣货路径）都直接可用，只需换路网数据来源。
- **验收标准**：跨楼层路线正确（电梯边被使用）；无障碍模式下楼梯边被排除；返回距离与预计耗时；起终点不可达时返回明确错误码而非 500；单元测试覆盖 ≥70%；单次规划 P95 < 200ms（demo 数据规模下）。

### M4 map-render

- **职责**：前端地图包。分层 SVG 底图渲染、缩放拖动、楼层切换、POI 与设施图标、路线绘制与动态展示、**点位标注工具**（在底图上点击生成/编辑 POI 坐标，供 M10 调用）。
- **对外接口**（TS 包导出组件）：`<IndoorMap>`、`<RouteLayer>`、`<PoiPicker>`、`useMapState()`。
- **依赖**：M0（类型）、M3（路线数据结构）。
- **独立运行**：`pnpm demo` 起 Vite，加载 mock 楼层 SVG 与 mock 路线，可交互。
- **复用摘出**：任何需要室内地图的产品直接用；`PoiPicker` 单独可用于标注类项目。
- **验收标准**：三层切换流畅；缩放拖动不丢路线；路线按楼层分段绘制并高亮当前层；`PoiPicker` 点击底图能输出坐标并回写；移动端与大屏分辨率均适配。

### M5 agent-orchestrator

- **职责**：本项目的技术核心。意图解析、工具注册表、工具调用循环（模型自主决定调用顺序）、多轮上下文管理、调用链 trace 落库、超时与失败降级、流式输出、输出协议（含 `voice_channel`/`avatar_channel` 预留字段）。
- **对外接口**：
  - `POST /api/v1/agent/chat`（SSE 流式）：入参 tenant_id、venue_id、device_id、session_id、message、context（当前楼层/位置）
  - `GET /api/v1/agent/sessions/{id}/trace`：返回完整调用链（作品集演示用）
  - `POST /api/v1/agent/tools`（内部）：工具注册与描述
- **内置工具集（V1）**：`poi.search`、`poi.detail`、`route.plan`、`promotion.list`、`coupon.list`、`facility.nearest`、`knowledge.query`（→M6）、`recommend.rank`（→M7）。
- **依赖**：M0、M1、M2/M3（通过工具）、M6、M7、M8。
- **独立运行**：`examples/chat_cli.py` 用 mock 工具跑通 10 条问句，打印每步 trace。
- **复用摘出**：换掉工具注册表就能变成客服 Agent、运营助手、数据问答 Agent——这是最有价值的可复用件。
- **验收标准**：20 条真实问句测试集通过率 ≥80% 且失败原因有记录；每轮对话可在 trace 接口看到完整工具调用序列与耗时；工具超时（可配置）触发降级且不中断会话；模型不可用时返回兜底话术 + 转关键词检索；prompt 全部在配置/数据库中，代码里无硬编码；单次问答 P95 < 8s（含模型耗时，流式首字 < 2s）。

### M6 knowledge-rag

- **职责**：知识入库与检索。文档切片、向量化、检索、重排、引用溯源、幻觉控制（无依据时明确说"没有相关信息"）。
- **对外接口**：`POST /api/v1/knowledge/documents`（入库）、`POST /api/v1/knowledge/query`（检索，返回片段 + 出处 + 相关度）、`DELETE /api/v1/knowledge/documents/{id}`。
- **依赖**：M0、M1、M8（知识内容来源）。
- **独立运行**：`examples/rag_demo.py` 灌 20 条商场知识文档，跑 10 个查询，打印召回与出处。
- **复用摘出**：任何企业知识库问答场景直接可用。
- **验收标准**：检索结果带出处 ID 与原文片段；相关度低于阈值时返回空而非硬凑；文档更新后重新索引（有测试）；召回评测集（20 问）Top3 命中率有量化数字并记录在 README。

### M7 recommender

- **职责**：8 因子打分排序 + 可解释理由生成。因子：距离、楼层差、营业状态、当前优惠、商户推荐权重、热度、目标类型匹配、用户当前所在位置。权重全部可配置（按租户/场地）。
- **对外接口**：`recommend.rank(candidates, context, weights) -> [{poi_id, score, reasons[]}]`（Python 包）；HTTP `POST /api/v1/recommend/rank`。
- **依赖**：M0、M1、M2。
- **独立运行**：`examples/rank_demo.py` 对 10 个候选 POI 打分并打印理由。
- **复用摘出**：本地生活、内容推荐、商品排序均可用，换因子即可。
- **验收标准**：权重可通过配置改变排序结果（有测试）；每个结果带可读理由（"距你 120 米 / 营业中 / 满 100 减 20"）；无候选时返回空列表而非报错；打分逻辑单元测试覆盖 ≥80%。

### A1 voice-adapter / A2 avatar-adapter（冻结）

- **职责**：只定义接口与空实现。A1：`transcribe(audio) -> text`、`synthesize(text) -> audio_url`；A2：`render_speech(text, emotion) -> render_command`、`idle()`。
- **验收标准**：接口定义完整；空实现返回"能力未启用"标准错误码；M5 输出协议含预留字段；M11/M12 有灰态入口；**接真实实现时不需要改 M5 与端层业务代码**（用 mock 实现验证这一点并写入测试）。

### M8 content-service

- **职责**：业务内容 CRUD 与状态机。POI、设施、活动（8 类）、优惠券、广告、AI 知识内容的增删改查、审核状态、版本记录；对外提供 Agent 工具所需的查询接口。
- **对外接口**：`/api/v1/pois`、`/api/v1/facilities`、`/api/v1/activities`、`/api/v1/coupons`、`/api/v1/ads`、`/api/v1/knowledge-items`（均含列表/详情/创建/更新/删除，带租户与角色校验）。
- **依赖**：M0、M1、M2。
- **独立运行**：`make demo` 起服务 + seed 数据，OpenAPI 文档可交互测试。
- **复用摘出**：任何内容运营后台的底座。
- **验收标准**：活动状态机（草稿→待生效→进行中→已结束）流转正确且有测试；商户角色只能改自己门店数据（权限测试）；优惠券领取有幂等控制（同一用户重复领取不产生两条）；所有写操作记录操作日志。

### M9 analytics-service

- **职责**：埋点事件入库与指标聚合。11 项指标：AI 咨询次数、用户搜索内容、店铺搜索排行、导航次数、热门目的地、商铺被推荐次数、优惠券领取次数、优惠券核销次数、导视设备使用次数、时段客流需求、（预留）转化漏斗。
- **对外接口**：`POST /api/v1/events`（批量上报）、`GET /api/v1/metrics/*`（各指标查询，带时间范围与维度）。
- **依赖**：M0、M1。
- **独立运行**：`examples/ingest_demo.py` 灌 1000 条模拟事件，查询各指标。
- **复用摘出**：任何需要行为埋点分析的项目。
- **验收标准**：事件写入幂等（重复上报不重复计数）；11 项指标全部可查且数值可核对；按天/按小时/按楼层/按设备维度可切；大数据量下查询有索引支撑（有 explain 记录）。

### M10 admin-web

- **职责**：商场运营后台。商场信息与楼层管理、地图与点位维护（调用 M4 的 `PoiPicker`）、POI 与设施管理、活动与优惠管理、AI 知识内容管理、设备列表（只读，V1 不做远程控制）、数据看板（调 M9）、租户切换（平台角色可见）、账号与角色管理。
- **依赖**：M0、M1、M4、M8、M9。
- **独立运行**：`pnpm dev` + mock API 模式（不依赖后端也能看界面）。
- **验收标准**：改一家店的营业时间后，Agent 回答立即反映变化（e2e 测试）；点位标注工具可用；非本租户数据不可见；表单校验完整；空态/加载态/失败态都有 UI。

### M11 screen-web

- **职责**：大屏端。全屏触屏 UI、AI 问答入口（文字输入 + 语音灰态）、推荐卡片、路线展示（调 M4）、二维码接力、闲置轮播广告、无障碍模式切换。
- **依赖**：M0、M4、M5、M12（共享组件）。
- **独立运行**：`pnpm dev` + mock 模式。
- **验收标准**：1080p 与 4K 全屏适配；触屏可用；问答流式输出有打字机效果；二维码扫码后手机端能接力同一路线；AI 超时/失败有兜底 UI（不白屏）。

### M12 mobile-h5

- **职责**：手机端。扫码进入（携带 session_id、venue_id、from、to、route_id）、路线继续展示、POI 搜索、AI 问答轻版、优惠查看。
- **依赖**：M0、M4、M5。
- **独立运行**：`pnpm dev` + mock。
- **验收标准**：扫码参数解析正确；接力后路线与大屏一致；微信内置浏览器可用（若做小程序则单独说明）；首屏加载 < 3s（demo 环境）。

### M13 deploy

- **职责**：容器化与环境管理。各服务 Dockerfile、docker-compose（dev/demo/prod 三套）、Nginx 与 HTTPS、数据库迁移执行、seed 数据、备份脚本、健康检查、一键部署脚本、日志收集。
- **依赖**：全部。
- **验收标准**：一台干净服务器执行一条命令完成部署并可访问；`/health` 全部服务返回正常；数据库迁移可重复执行且幂等；备份脚本能产出可恢复的 dump；三套环境配置分离且 `.env` 不入库。

---

## 7. 核心数据模型（概览）

> 完整 DDL 见 PRD 第 6 节。此处只列模块归属与关系，便于理解边界。

| 表 | 归属模块 | 关键说明 |
| :--- | :--- | :--- |
| tenants、users、roles、user_roles、permissions | M1 | 多租户与 RBAC，所有业务表的外键源头 |
| venues、floors、map_layers | M2 | 场地与楼层，一张底图一个 layer |
| pois、facilities、poi_categories（数据字典） | M2/M8 | POI 与设施；分类体系按租户可配置 |
| route_nodes、route_edges | M3 | 路网图；边带权重、垂直交通类型、无障碍标记 |
| activities、coupons、coupon_claims、ads | M8 | 活动 8 类；优惠领取带幂等键 |
| knowledge_documents、knowledge_chunks、knowledge_embeddings | M6 | 文档 → 切片 → 向量 |
| agent_sessions、agent_messages、agent_traces、agent_tools | M5 | trace 是作品集亮点，必须完整 |
| recommend_weights、recommend_logs | M7 | 权重可配置，打分结果留痕 |
| events、metrics_daily | M9 | 埋点明细 + 日聚合 |
| devices | M1/M13 | 设备注册、所属场地楼层、在线状态、版本（V1 只读，不做 OTA） |

**关系主线**：`tenants 1—N venues 1—N floors 1—N pois`；`floors 1—N route_nodes`；`route_edges` 连接同层节点或跨层垂直交通；`pois 1—N activities/coupons`；`agent_sessions N—1 venues`，`agent_traces N—1 agent_sessions`。

---

## 8. 统一契约规范（M0 定稿内容）

### 8.1 统一响应体

```json
{
  "code": 0,
  "message": "ok",
  "data": {},
  "trace_id": "tr_20261103_abc123",
  "server_time": "2026-11-03T21:00:00+08:00"
}
```

`code=0` 为成功；非 0 为业务错误，HTTP 状态码仍按语义返回（400/401/403/404/409/422/429/500/503）。

### 8.2 错误码分段

| 段 | 含义 | 示例 |
| :--- | :--- | :--- |
| 1xxx | 通用与鉴权 | 1001 未认证、1003 无权限、1004 租户不存在 |
| 2xxx | 空间与路径 | 2001 POI 不存在、2003 起终点不可达、2004 路网未构建 |
| 3xxx | AI 能力 | 3001 模型不可用、3002 工具调用超时、3003 无相关知识、3004 已降级为关键词检索 |
| 4xxx | 业务内容 | 4001 活动状态不允许、4002 优惠券已领完、4003 重复领取 |
| 5xxx | 冻结能力 | 5001 语音能力未启用、5002 数字人能力未启用 |
| 9xxx | 系统 | 9001 服务不可用、9002 限流 |

### 8.3 必带请求头

`X-Tenant-Id`、`X-Trace-Id`（端层生成，无则网关补）、`Authorization`、`X-Device-Id`（大屏/手机端必带）、`X-Client`（admin/screen/mobile）。

### 8.4 分页与时间

分页统一 `page`（从 1 起）+ `page_size`（默认 20，上限 100），响应含 `total`。时间统一 ISO 8601 带时区，数据库存 UTC，展示层转 `Asia/Shanghai`。**时间类型、主键类型（统一 BIGINT 自增或统一 UUID，二选一并写进 DECISIONS.md）、枚举大小写全局统一，禁止混用。**

### 8.5 事件 schema

`{event_id, tenant_id, venue_id, event_type, subject_type, subject_id, actor_type, actor_id, payload, occurred_at, trace_id}`。事件类型枚举在 M0 定义，新增需登记。

---

## 9. demo → 生产：7 个开关

| 开关 | demo 阶段做法 | 转生产改什么 | 代码是否要改 |
| :--- | :--- | :--- | :--- |
| 多租户 | 所有表带 `tenant_id`，seed 两个租户（1 个有数据、1 个空） | 新增租户记录 + 分配账号 | 否 |
| 鉴权 | 四角色接口全部按 RBAC 设计，demo 用固定 token 登录 | 接真实登录、密码策略、会话过期、审计 | 否（只换实现） |
| AI 供应商 | Provider 抽象层，模型名/超时/重试/降级全在配置 | 换模型或加备用供应商 | 否 |
| 数据层 | 全部走 migration + seed 脚本 | 生产库跑同一套迁移；加只读副本 | 否 |
| 可观测 | 结构化日志 + trace_id 贯穿 + 埋点入库 | 接告警（错误率、AI 超时率、慢查询） | 否 |
| 部署 | 容器化 + 三套环境 + 健康检查 + 一键脚本 | 换域名/规格/CDN；加自动备份与回滚 | 否 |
| 降级兜底 | AI 挂 → 关键词检索；路线算不出 → 楼层平面 + 文字指引；服务不可用 → 静态信息页 | 加人工客服入口、熔断阈值调优、限流 | 否 |

**判断标准**：如果转生产时需要改业务代码，说明这个开关没做对，回去补。

---

## 10. 12 周排期与每周验收

| 周 | 模块 | 每周验收物（能演示/能跑的东西） |
| :--- | :--- | :--- |
| 1 | M0 + M1 + M2 | 契约定稿并冻结；platform-core 示例跑通（两租户隔离 + 鉴权 + trace）；虚拟商场数据灌入（3 层、60—80 POI、20 设施、10 活动优惠）；仓库脚手架与 CI 就绪 |
| 2 | M4 + M10 的点位标注 | 浏览器里看到分层 SVG 地图，可缩放拖动切层；`PoiPicker` 点一下生成 POI 并落库 |
| 3 | M3 | 选两个店出跨楼层路线，显示分段、距离、预计耗时；无障碍模式生效；单元测试通过 |
| 4 | M6 | 知识入库 + 检索可用，20 问评测集 Top3 命中率有数字 |
| 5 | M5 | Agent 跑通 20 条问句，SSE 流式输出，trace 接口能看到完整工具调用链 |
| 6 | M7 + M8 | "今天吃什么划算"返回带优惠、带理由、带路线入口的结果；content-service 全部 CRUD + 状态机 + 权限测试通过 |
| 7 | M10 | 运营后台可维护 POI/活动/优惠/知识/地图；改数据后 Agent 回答立即变化（e2e 验证） |
| 8 | M12 + M11 + A1/A2 | 大屏问路 → 扫码 → 手机接力同一路线；语音与数字人入口为灰态且接口就绪 |
| 9 | M9 | 埋点全链路打通，11 项指标看板可查 |
| 10 | M13 | 公网 demo 地址上线；一键部署脚本在干净环境验证过；备份与健康检查可用 |
| 11 | 文档 | ARCHITECTURE/DECISIONS 补全；每模块 README 达标；3 篇难点解析写完 |
| 12 | 作品集 | 2 分钟演示视频；发布到程序员客栈与 GitHub；复盘记录（做了什么、砍了什么、为什么） |

**进度红线**：第 6 周末若 M3/M5/M6 任一未完成，立即启动砍范围预案（砍 M9 看板 → 砍 M7 个性化 → 砍 M11 大屏改为 H5 全屏模拟），保核心。

---

## 11. CLAUDE.md 建议内容

```markdown
# 空间智能体导视平台

一句话：场景无关的空间智能体内核（多租户 + 空间数据 + 路径规划 + Agent 编排 + RAG + 推荐），首个场景为商场 AI 导视。

## 必读文档
- ARCHITECTURE.md：架构、模块契约、工程约定（冲突时以它为准）
- PRD.md：功能规格、数据模型 DDL、API 定义、异常与降级、验收标准
- DECISIONS.md：已定技术决策，不要推翻

## 技术栈
Python 3.12 + FastAPI + SQLAlchemy(async) + PostgreSQL 16 + PostGIS + pgvector + Alembic
前端 TypeScript + Vite + React + pnpm workspace；地图为分层 SVG（不使用商业室内地图 SDK）
容器 Docker + docker-compose；三套环境 dev/demo/prod

## 开发规范
- 一次只做一个模块的一个子任务，改动 ≤400 行
- 只能改 packages/<当前模块>/，禁止跨包 import 其他模块内部实现（CI 会拦）
- 数据库变更只写 Alembic 迁移，禁止改已有迁移文件
- 所有配置从环境变量读，禁止硬编码密钥、模型名、prompt、租户 ID
- 新接口先更新 packages/api-contract/openapi/，再写实现
- 每个功能同时写测试；测试可独立运行，外部依赖用 mock
- 提交信息格式：feat(M3): xxx / fix(M5): xxx / docs: xxx

## 禁止事项
- 不要引入 PRD 未列出的第三方依赖
- 不要直接修改数据库表结构
- 不要修改 .env 中已有变量名
- 不要跳过权限与租户校验
- 不要在代码中硬编码密钥
- 日志中不得输出密码、Token、手机号原文
- 关键写入接口必须幂等
- 不要把 demo 逻辑写成 if demo 分支，用配置开关

## 常用命令
- 起全套：docker compose up -d
- 单模块 demo：cd packages/<module> && make demo
- 跑测试：make test / pnpm -r test
- 迁移：make migrate && make seed
```

---

## 12. Claude Code 协作纪律（决定你 12 周后是真懂还是假懂）

1. **先方案后代码**：每个任务要求它先输出不超过 15 行的实现方案，你确认后再写。
2. **DECISIONS.md 一行一决策**：格式 `2026-11-05 | M3 | 用 networkx 而非自研图算法 | 理由：成熟、支持 A*、便于替换 | 放弃：自研（维护成本）`。这份文件是你的面试答案库，也是防止 AI 后期推翻前期架构的锚。
3. **每模块必须有测试**，测试是唯一能自动验证 AI 没写错的手段，路径规划与推荐打分尤其要有。
4. **合上代码复述数据流**：每完成一个模块，不看代码用自己的话讲一遍"请求进来后经过哪些模块、读写哪些表、返回什么"。讲不顺就回去补——这条是作品集与负债的分界线。
5. **每周一次架构回顾**：对照第 3.2 节 7 条原则和第 4.1 节 8 条约定自查，发现偏离当周修正，不要攒到最后。

---

## 13. 作品集交付清单

| 材料 | 说明 | 负责周 |
| :--- | :--- | :--- |
| 公网 demo 地址 | 可直接点开体验，含大屏模拟页与手机页 | 10 |
| 2 分钟演示视频 | 脚本见 PRD 附录；结构：一句话定位 → 完整用户旅程 → 后台改数据 → 数据看板 → 架构与可复用性 | 12 |
| 架构图 | 本文档第 3 节的重绘版（用绘图工具画，不要截图 ASCII） | 11 |
| DECISIONS.md | 全部技术决策与理由 | 持续 |
| 3 篇难点解析 | ①跨楼层路径规划的图建模与权重设计 ②Agent 工具编排与幻觉控制 ③多租户与可复用内核的边界设计 | 11 |
| 每模块 README | 做什么/接口/如何单独跑/示例/如何摘出复用 | 11 |
| Agent trace 可视化 | 一次问答的完整工具调用链截图，这是最能证明"我懂 Agent"的材料 | 5 |
| 复盘记录 | 做了什么、砍了什么、为什么砍、下次怎么改 | 12 |

**演示数据合规要求**：虚拟商场的名称、店铺、优惠全部自行虚构，可参考真实商场的业态结构（餐饮集中在高层、影院在角落、母婴室邻近卫生间），**不得直接使用真实商场名称、真实商户名单与真实促销信息**。

---

## 14. 风险与对策

| 风险 | 影响 | 对策 |
| :--- | :--- | :--- |
| 范围失控（141 条需求诱惑你加功能） | 直接导致做不完 | 每周对照第 2 节冻结表，新增需求一律记入 V2；第 6 周检查进度红线 |
| 接口漂移 | 模块对不上，联调地狱 | M0 第 1 周冻结；改契约必须记 DECISIONS.md 并跑 e2e |
| 地图数据录入耗时被低估 | 第 2—3 周卡死 | 点位标注工具提前到第 2 周做（M4 + M10 联动），用工具录入而非手写坐标 |
| AI 生成的代码自己看不懂 | 面试被追问即崩 | 第 12 节纪律 4（复述数据流）+ 每模块测试 + DECISIONS.md |
| AI 调用成本失控 | 预算超支 | Provider 抽象层设每日调用上限与超限降级；⚠️ 具体单价需按所选模型自行询价 |
| 单点故障导致 demo 白屏 | 演示翻车 | 第 9 节降级兜底必须在第 5—8 周就实现，不要留到最后 |
| 一个人做 14 个模块的管理负担 | 每个都做一半 | 宁可少做一个模块，不留半成品；模块完成定义 = 能独立跑通 + 有测试 + README 达标 |

## 15. 开源复用清单与选型纪律

**总原则：不造轮子。** 只有三种情况允许自研：① 开源方案 license 与未来商用交付不兼容；② 开源方案与多租户/模块契约边界冲突，改造成本高于自研；③ 该模块是项目的核心复用资产且业务逻辑无法由通用库覆盖（如 M3 的业务权重层、M5 的业务工具集）。

### 15.1 已核实的候选（开工前仍需 CC 实际核验当前状态）

| 能力 | 候选 | 与本项目模块 | 说明 |
| :--- | :--- | :--- | :--- |
| 室内 SVG 地图 + 寻路 | `KnotzerIO/indoor-wayfinder`（Pathpal） | M4 + M3 | React + Vite + TS + Tailwind + SVG + Dijkstra，技术栈与本项目完全一致，建议作为 M4 起点 |
| 自托管室内导航整体方案 | `openindoormaps/openindoormaps` | M4/M10 参考 | 含地图编辑与导航，可参考其数据模型与编辑器设计 |
| 3D 室内地图 | `Indoor3D`（three.js） | 备选 | 自带购物中心 JSON 数据示例；3D 显著增加工作量，V1 不建议 |
| 室内寻路算法库 | Navigine 开源寻路库 | M3 | 面向室内路网图的 wayfinding 算法，可替代自研算法层 |
| Agent 编排 | LangGraph（MIT） | M5 | 有状态图、循环、检查点持久化（SQLite/PostgreSQL/Redis） |
| 检索与索引 | LlamaIndex（MIT） | M6 | 检索专用抽象，比手写 RAG 少写三到四成代码 |
| 全栈 RAG 平台 | RAGFlow | M6 备选 | 文档解析强、自带 Web UI 与评估；体量大（建议 ≥16G 内存），Agent 能力弱于专用框架，协议以仓库 LICENSE 为准 |
| 模型供应商抽象 | LiteLLM | M5/M1 | 多供应商统一接入，带 cooldown，单 Key 限流自动切换 |
| Agent 可观测 | Langfuse | M5 | 调用链与 token 统计，可直接充当 trace 可视化（作品集亮点） |
| 协议安全的存储组合 | PostgreSQL（PostgreSQL License）+ Valkey（BSD-3）+ RustFS（Apache-2.0） | M13 | 避开 MySQL CE（GPL）与 MinIO 社区版（AGPL v3），降低未来商用交付的合规不确定性 |
| 后台 UI | shadcn/ui 或 Ant Design；Refine / React Admin | M10 | 由 CC 按 license、最近提交、与 Tailwind 兼容性核验后二选一 |
| 全栈脚手架参考 | tiangolo `full-stack-fastapi-template` | 全局 | 参考目录结构、鉴权与迁移组织方式，不整体套用 |
| 室内定位（V2） | MIPNS3.0、FIND | V2 | 手机多传感器融合 / WiFi 指纹，对应蓝点导航 |

⚠️ 上表项目的 star 数、维护活跃度、license 细节随时间变化，**必须由 CC 在选型时实际核验**，不得直接采信本表；核验结论写入 `REUSE.md`。

### 15.2 选型纪律（写进 CI 与 CLAUDE.md）

1. 引入任何新依赖前，先在 `REUSE.md` 登记：名称、版本、license、用途、替代方案、选择理由。**未登记的依赖禁止进 `pyproject.toml` / `package.json`**（CI 加检查）。
2. license 白名单：Apache-2.0、MIT、BSD、PostgreSQL License。GPL/AGPL 类默认拒绝，确需使用必须由我确认并记录法务风险。
3. 复用方式分三级并在 `REUSE.md` 标明：**作为依赖引入**（首选）→ **复制部分源码并注明出处与 license**（次选，须保留版权声明）→ **仅参考实现，自己写**（末选，说明理由）。
4. 复用不得破坏模块边界：引入的开源件必须封装在所属模块内部，对外仍只暴露 M0 契约。**禁止把第三方框架的类型直接泄漏成跨模块接口**——否则将来换框架要改所有模块，复用价值归零。
5. AI 层技术栈按"最小陌生面"原则确定为：**LangGraph（编排，唯一引入的 AI 框架）+ pgvector（向量存储）+ 自建 RAG 管道 + 自建 Provider 抽象 + 自建 trace**。V1 明确不引入 LlamaIndex、LiteLLM、Langfuse、RAGFlow、Dify、PostGIS、Refine/React Admin、Celery、Kubernetes；将来确需引入，必须先说明理由、登记 `REUSE.md`，并封装在模块内部，禁止把第三方类型泄漏成跨模块接口。

### 15.3 配套文件

- `CLAUDE.md`：仓库入口文件，已单独成文（含角色分工、复用优先原则、边界约束、任务工作流、禁止事项、完成定义）
- `CC 提示词手册`：会话启动、通用任务、开源选型、契约先行、TDD、代码审查、Bug 定位、各阶段专用提示词、验收自证、反模式对照，以及建议固化的 `.claude/commands/*.md` 命令文件

---

内容由 AI 生成
