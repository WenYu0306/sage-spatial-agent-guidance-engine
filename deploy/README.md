# M13 deploy — 部署、迁移与 demo 数据

## 做什么

容器编排（`docker-compose.yml`）、Alembic 迁移（**唯一改表入口**）、虚拟商场 demo 数据 seed（手册 7.2）、Agent 评测基线。本目录不承载业务逻辑。

## 对外接口

- Makefile 目标：`make compose-up` / `make migrate` / `make seed` / `make compose-down`
- `deploy/seed/seed.py`：`run_seed() -> dict[str, int]`（幂等执行并返回各表行数，供测试调用）；`count_rows()` 行数统计
- 数据源（可读 YAML，全部虚构）：`deploy/seed/data/*.yaml` 共 10 个文件
- 评测基线：`deploy/seed/data/eval_baseline.yaml`（20 问句，供 `scripts/run_agent_eval.py` 读取）

## 如何单独运行

```bash
make compose-up        # 起 postgres + redis
make migrate           # Alembic 升到 head（0001 空 + 0002 demo 表）
make seed              # 灌虚拟商场数据（可重复执行）
uv run pytest deploy/seed/tests   # 26 个测试：表结构/数据源结构/幂等
```

## 示例

```
== seed 完成，各表行数 ==
  tenants: 1 行      pois: 88 行          activities: 6 行
  users: 1 行        poi_categories: 32 行  coupons: 4 行
  roles: 5 行        floors: 3 行          knowledge_documents: 100 行
  venues: 1 行       map_layers: 3 行
```

幂等定义：同一数据源连续执行两遍，各表行数不变（首遍 INSERT，后续 UPDATE，不删不重灌）。

## 如何摘出复用到其他项目

"YAML 源文件 + 自然键幂等 upsert + 行数统计"三件套可直接搬去任何需要演示数据的项目：

1. 复制 `deploy/seed/{seed.py,data/,tests/}`，改 YAML 与对应 handler；
2. 幂等思路通用：有唯一约束的表用 `ON CONFLICT DO UPDATE`（floors/map_layers/poi_categories），无约束的按自然键先查后改插（pois/activities/knowledge_documents）；
3. JSONB 字段一律 `psycopg.types.json.Jsonb()` 显式包装（psycopg3 不自动适配 dict）；
4. 验收方式通用：结构测试（边界/引用/规模）+ 幂等测试（两遍行数一致）。
