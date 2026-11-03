# DECISIONS.md — 技术决策记录（每个决策一行）

> 规则：已定决策不得推翻；要改先提出，改后在此补一行。

- 2026-11-03 D-001 技术栈按 CLAUDE.md 第 4 节冻结（后端/前端/AI 层/工程四类，见 CLAUDE.md，不在此重复）。
- 2026-11-03 D-002 主键统一 BIGINT IDENTITY、时间统一 TIMESTAMPTZ 存 UTC 展示 Asia/Shanghai、枚举统一小写下划线、金额 NUMERIC(12,2)（PRD 6.0；ARCHITECTURE 8.4 要求落 DECISIONS）。
- 2026-11-03 D-003 Python 工作区选 uv（备选 poetry）：快、官方支持 workspace 成员独立打包、单文件锁；首批 dev 依赖 ruff/import-linter/pytest/alembic/psycopg 已登记 REUSE.md。
- 2026-11-03 D-004 M0 契约源 = packages/api-contract/schemas/（JSON Schema 2020-12 + YAML 登记表），make validate/gen 生成的 Pydantic/TS 两端类型，生成物入库且 CI 检查同步（契约先行）。
- 2026-11-03 D-005 错误码六段按 ARCHITECTURE 8.2（1xxx 通用鉴权 / 2xxx 空间路径 / 3xxx AI / 4xxx 业务内容 / 5xxx 冻结能力 / 9xxx 系统）；码表唯一登记于 schemas/error-codes.yaml，validate 强制唯一性与分段归属。
- 2026-11-03 D-006 事件 schema 必填字段按 ARCHITECTURE 8.5 冻结；event_type 枚举登记于 event.schema.json 的 event_types 字段（当前为空，M5/M9 任务时填充），actor_type 枚举待 M1 定稿。
- 2026-11-03 D-007 前端边界检查脚手架阶段用 eslint-plugin-boundaries + .js 演示文件验证；前端代码落地时引入 @typescript-eslint 并升级规则（届时登记 REUSE.md）。
- 2026-11-04 D-008 demo 数据源 = deploy/seed/data/*.yaml，自然键幂等 upsert（首遍 INSERT 后续 UPDATE，不删不重灌）；评测基线为文件资产不入库，运行记录仍写 packages/agent-orchestrator/EVAL.md。
- 2026-11-04 D-009 poi_intro 知识文档由 pois 数据派生生成（不手写），保证文档与数据一致；"100 篇"口径 = 68 店铺介绍 + 17 场地指南 + 15 FAQ，设施不生成介绍。
- 2026-11-04 D-010 演示运营账号口令走环境变量 SEED_DEMO_ADMIN_PASSWORD（bcrypt cost 12）；重复 seed 不覆写已存在账号的口令。
- 2026-11-04 D-011 M3 权重按 PRD 6.3：weight=通行时间(秒)+惩罚，seed 预计算入库、引擎只读；电梯 ride 15s/扶梯 ride 25s 为 demo 构造参数（PRD 只给惩罚 45/15s）；扶梯东(x=850)上行、西(x=350)下行且非无障碍，跨层无障碍唯一通道为直梯。
- 2026-11-04 D-012 前端测试用 node:test 原生跑 TS（Node 24 strip types），不引入 vitest；组件交互以纯函数抽测 + 演示页人工验证，组件级 DOM 测试随 M10 后台任务再评估。
- 2026-11-04 D-013 RAG 切片与限额：token 估算 CJK 1 字≈1 token/其余 4 字符≈1 token；切片 300-500、重叠 50（重叠预算受 500 上限约束）；每日限额按 API 调用次数计（进程内计数，多进程时 M5 换 Redis）；入库分批（16 条/次）调 embedding。
- 2026-11-04 D-014 embedding 维度 1024（EMBED_DIM，Provider 经 dimensions 参数适配 text-embedding-3-small 等 Matryoshka 模型）；postgres 镜像换 pgvector/pgvector:pg16（直连 Docker Hub 超时，compose 走 daocloud 源）；检索阈值默认 0.35（RAG_THRESHOLD 可配），评测 hit 定义见 scripts/run_agent_eval.py。
- 2026-11-04 D-013 更正：入库批大小改为配置 EMBED_BATCH_SIZE（默认 10，百炼 embeddings 单批上限），非固定 16；批超限报错经 ProviderUnavailableError 语义暴露。
- 2026-11-04 D-015 意图解析用 prompt 约束 + jsonschema 校验（不用 response_format 参数，保 DeepSeek 兼容）；SSE delta 粒度为按句（provider.chat 非流式，token 级流式留增强）。
- 2026-11-04 D-016 工具双通道：数据类（poi/promotion/coupon/facility）demo 阶段直读共享 PRD-DDL 表（M8 服务化后换 endpoint）；算法类（route.plan/knowledge.query）走兄弟模块 HTTP 服务（import-linter 禁跨包 import）。
- 2026-11-04 D-017 degraded 语义=回答完整性受损（硬错误/知识降级/预算超限/幻觉拦截）；路线文字指引等工具级提示只记 error_code 不拉低整轮状态。
- 2026-11-04 D-018 platform_core 定位 L0 基础层（同 api-contract），各包可 import，在模块独立性契约中以 ignore_imports 显式豁免。
