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
| bcrypt | >=4.2 | Apache-2.0 | seed 演示运营账号口令哈希（PRD 6.1 指定 bcrypt cost≥12 存储格式） | argon2-cffi、passlib | pyca 官方实现、维护活跃；PRD 已指定 bcrypt 格式，无选型分歧；仅 demo 数据准备阶段使用 |
| pytest-cov | >=7.1 | MIT | 测试覆盖率报告（M3 要求 ≥70%） | coverage.py 裸用 | pytest 官方插件生态事实标准；CLAUDE.md 完成定义需要覆盖率报告 |
| networkx | >=3.7 | BSD-3-Clause | M3 路网图数据结构与 A*/Dijkstra 算法底座 | Navigine/Indoor-Routing-Library（C++、无 license、20 个月未动）、自写图算法 | 手册 7.3 选型胜出：CLAUDE.md 冻结选型；电梯/扶梯惩罚、无障碍、错误码等业务权重层全部自建其上；BSD 宽松可商用 |
| react-zoom-pan-pinch | ^4.2 | MIT | M4 地图缩放/拖动引擎（自建分层 SVG 组件内使用） | svg-pan-zoom、@use-gesture/react、自写手势 | 手册 7.3 选型胜出：1958★、5 天前仍在提交；Pathpal（无 license、停更原型）与 OpenIndoorMaps（MapLibre 地理坐标栈，与 V1 SVG 平面坐标决策冲突）仅作交互参考 |
| react / react-dom / vite / typescript | ^19 / ^7 / ^5.9 | MIT / MIT / MIT / Apache-2.0 | M4 前端运行时与构建（CLAUDE.md 第 4 节冻结栈，首次进入 package.json 时补登记） | — | 栈在 CLAUDE.md 已定；按"未登记依赖不进 package.json"纪律在此补记来源 |
| tailwindcss / @tailwindcss/vite / @tanstack/react-query | ^4.1 / ^5.90 | MIT | M10 后台样式与数据请求层（CLAUDE.md 冻结栈；Tailwind v4 走 vite 插件零配置） | unocss、CSS Modules、SWR | 栈已定；v4 插件化最省配置，react-query 五态缓存/重试语义贴合 PRD 9 |
| typescript-eslint | ^8 | MIT | TS 代码的 eslint 解析与 lint（D-007 预留，M4 落地时引入） | — | 7.1 决策预留的接线点；map-render 首批 TS 代码落地按约引入（补登记：此前补丁锚点静默失效，本行为补录） |
| openai（Python SDK） | >=2.x | MIT | LLMProvider 的 OpenAI 兼容 HTTP 底座（embed/chat，M6/M5） | 手写 httpx 封装 | CLAUDE.md 第 4 节钦定"OpenAI 兼容 SDK"；官方维护、重试/超时现成；Provider 抽象仍自建在其上 |
| langgraph | >=1.2 | MIT | M5 Agent 有状态编排（StateGraph/条件边/checkpointer） | 自写状态机 | CLAUDE.md 第 4 节钦定的唯一 AI 框架；手册 7.4 指定 |
| langgraph-checkpoint-postgres | >=3.2 | MIT | LangGraph 会话检查点持久化（PostgresSaver） | 自写存档 | langgraph 官方配套，多轮上下文必需 |
| fastapi | >=0.162 | MIT | M5 SSE 端点与后续全部 HTTP API | flask、starlette 裸用 | CLAUDE.md 第 4 节钦定栈；SSE 用 StreamingResponse 无需额外库 |
| uvicorn | >=0.54 | BSD-3-Clause | ASGI 服务器 | hypercorn | fastapi 官方推荐组合 |
| httpx | >=0.28 | BSD-3-Clause | 模块间 HTTP 客户端（M5 工具层调兄弟模块服务）+ FastAPI TestClient 依赖 | requests | starlette TestClient 官方依赖；async 友好 |
| PyJWT | 2.15 | MIT | M1 认证：access/refresh token 签发与验证（HS256，PRD 9 安全表） | python-jose（维护活跃度下滑）、authlib（含 OAuth，超出需求） | API 最小（encode/decode 两个函数），持续维护，主动警告弱密钥长度 |
| qrcode (npm) | ^8 | MIT | M11 大屏「发到手机」二维码生成（扫码落地 M12 /m/route/{id}） | 自绘 QR 编码器（不现实）、qr-server（引入服务端依赖） | 纯前端生成零服务依赖，持续维护，仅 1 个运行时依赖 |
| redis-py | 8.1 | MIT | token 登出黑名单（SETNX+TTL 自动过期，PRD 9：Redis 或数据库表） | 数据库表（需新迁移与清理任务） | Redis 7 已在技术栈内，黑名单仅 5 行调用；内存后端为单进程 demo 降级 |

## 待引入（后续任务按流程调研后登记）

- FastAPI / SQLAlchemy 2.x / asyncpg — M8/M2 任务时登记
- LangGraph — M5 任务时登记
- 已按 7.3 选型登记：networkx（M3）、pytest-cov（M3）、react-zoom-pan-pinch（M4）；Pathpal 与 OpenIndoorMaps 不引入，仅作交互参考（理由见上表）
