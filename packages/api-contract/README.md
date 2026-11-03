# api-contract（M0）

统一契约包：所有跨模块通信的响应体、错误码、事件 schema、请求头、分页约定在此定稿。

## 做什么

- `schemas/`：契约源文件（JSON Schema 2020-12 + YAML 登记表）
  - `response.schema.json`：统一响应体（8.1）
  - `error-codes.yaml`：错误码注册表，六段（8.2），validate 强制唯一性与分段
  - `headers.yaml`：必带请求头（8.3）
  - `pagination.schema.json`：分页请求/响应约定（8.4）
  - `event.schema.json`：领域事件 schema（8.5）
- `openapi/common.yaml`：各模块 OpenAPI 文件的共享组件骨架
- `generated/`：`make gen` 产出的 Pydantic 模型与 TS 类型（入库，禁止手改）

## 对外接口

- `make validate`：契约校验（错误码唯一性/分段、Schema 合法性、examples 自校验、OpenAPI 骨架）
- `make gen`：生成 `generated/python/*_models.py`（Pydantic v2）与 `generated/ts/*.d.ts`
- 契约变更流程见 ARCHITECTURE.md 4.1 第 4 条：先改这里 → DECISIONS.md 记一行 → 同步受影响模块 → 跑 e2e

## 如何单独运行

```bash
uv sync                 # 仓库根执行一次
make validate           # 无需数据库
make gen                # 需要 pnpm（json2ts）与 uv
```

## 示例

```bash
$ make validate
== M0 契约校验 ==
  [ ok ] error-codes.yaml：6 个段、17 个错误码，唯一性与分段检查通过
  ...
```

## 如何摘出复用到其他项目

复制 `schemas/ + openapi/ + scripts/` 三个目录到目标仓库，改 `scripts/gen.py` 里的输出路径即可；
错误码六段思路（1xxx 通用/2xxx 领域/3xxx AI/5xxx 冻结/9xxx 系统）可直接沿用。
