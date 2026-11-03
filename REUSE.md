# REUSE.md — 已选定开源依赖登记表

> 规则（CLAUDE.md 第 4 节）：未登记的依赖进 pyproject.toml / package.json 前必须先在此登记。
> 引入任何新依赖前，先按手册第 2 节流程调研并在此登记；改动本表先提出。

## 工程与工具链

| 名称 | 版本约束 | License | 用途 | 替代方案 | 为何选它 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| uv | >=0.9 | MIT/Apache-2.0 | Python workspace 与虚拟环境管理 | poetry | 快、官方支持 workspace、单文件锁 |
| ruff | >=0.13 | MIT | Python lint | flake8+isort | 快、单工具替代多件、已是事实标准 |
| import-linter | >=2.3 | MIT | 强制模块边界（跨包 import 检查） | 手写 CI 脚本 | 直接表达"内核禁依赖业务"契约，CI 可拦截 |
| pytest | >=8.3 | MIT | 测试框架 | unittest | 事实标准，插件生态 |
| alembic + psycopg[binary] | >=1.14 / >=3.2 | MIT / LGPL-3.0 | 数据库迁移与脚本驱动（唯一改表入口） | 手写 SQL 脚本 | SQLAlchemy 官方配套、迁移链可回滚；psycopg 为 LGPL-3.0 库依赖（动态链接、不修改其源码），不触发源码开放义务；异步驱动 asyncpg（Apache-2.0）待 M1 引入时登记 |
| eslint | ^9.39 | MIT | JS/TS lint | — | 事实标准 |
| eslint-plugin-boundaries | ^5.0 | MIT | 前端跨包 import 边界检查 | — | 与 import-linter 对应的 TS 侧边界工具 |
| json-schema-to-typescript | ^15.0 | MIT | 契约 → TS 类型生成 | openapi-typescript | 以 JSON Schema 为契约源，链路最短 |
| datamodel-code-generator | >=0.28 | MIT | 契约 → Pydantic v2 模型 | 手写模型 | 从同一 JSON Schema 源生成，保证两端一致 |
| pydantic / jsonschema / pyyaml | >=2.9 / >=4.23 / >=6.0 | MIT / MIT / MIT | 契约校验与生成的基础库 | — | validate/gen 的支撑库，随 api-contract 引入 |

## 待引入（后续任务按流程调研后登记）

- FastAPI / SQLAlchemy 2.x / asyncpg — M1 任务时登记
- networkx — M3 任务时登记
- LangGraph — M5 任务时登记
