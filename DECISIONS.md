# DECISIONS.md — 技术决策记录（每个决策一行）

> 规则：已定决策不得推翻；要改先提出，改后在此补一行。

- 2026-11-03 D-001 技术栈按 CLAUDE.md 第 4 节冻结（后端/前端/AI 层/工程四类，见 CLAUDE.md，不在此重复）。
- 2026-11-03 D-002 主键统一 BIGINT IDENTITY、时间统一 TIMESTAMPTZ 存 UTC 展示 Asia/Shanghai、枚举统一小写下划线、金额 NUMERIC(12,2)（PRD 6.0；ARCHITECTURE 8.4 要求落 DECISIONS）。
- 2026-11-03 D-003 Python 工作区选 uv（备选 poetry）：快、官方支持 workspace 成员独立打包、单文件锁；首批 dev 依赖 ruff/import-linter/pytest/alembic/psycopg 已登记 REUSE.md。
- 2026-11-03 D-004 M0 契约源 = packages/api-contract/schemas/（JSON Schema 2020-12 + YAML 登记表），make validate/gen 生成的 Pydantic/TS 两端类型，生成物入库且 CI 检查同步（契约先行）。
- 2026-11-03 D-005 错误码六段按 ARCHITECTURE 8.2（1xxx 通用鉴权 / 2xxx 空间路径 / 3xxx AI / 4xxx 业务内容 / 5xxx 冻结能力 / 9xxx 系统）；码表唯一登记于 schemas/error-codes.yaml，validate 强制唯一性与分段归属。
- 2026-11-03 D-006 事件 schema 必填字段按 ARCHITECTURE 8.5 冻结；event_type 枚举登记于 event.schema.json 的 event_types 字段（当前为空，M5/M9 任务时填充），actor_type 枚举待 M1 定稿。
- 2026-11-03 D-007 前端边界检查脚手架阶段用 eslint-plugin-boundaries + .js 演示文件验证；前端代码落地时引入 @typescript-eslint 并升级规则（届时登记 REUSE.md）。
