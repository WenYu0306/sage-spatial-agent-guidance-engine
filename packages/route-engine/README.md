# M3 route-engine — 路网规划引擎

## 做什么

从 `route_nodes`/`route_edges`（deploy/seed 产出）构建有向图，用 networkx A* 求**最短时间**路径；支持无障碍模式（剔除 `accessible=false` 边）；不可达抛 `2003`、路网未构建抛 `2004`（M0 错误码表）。权重在 seed 阶段按 PRD 6.3 预计算入库：步行 1.2m/s、电梯 +45s、扶梯 +15s、楼梯台阶×2s（引擎只读 `weight` 列）。

## 对外接口

- `route_engine.graph`：`build_graph(nodes, edges, scale_meter, accessible_only)` / `plan(g, start, goal, scale_meter)` → `RouteResult{node_path, segments[], total_distance_meter, total_time_s}`；`RouteError.code` 对应 M0 错误码
- `route_engine.db`：`load_route_graph(tenant_code, venue_name)` 从库加载
- CLI：`uv run --package route-engine python -m route_engine.demo <起点POI> <终点POI>`

## 如何单独运行

```bash
make compose-up && make migrate && make seed   # 依赖 demo 数据
set -a; . ./.env; set +a
uv run --package route-engine python -m route_engine.demo 云雀优选超市 巨幕星云影院
uv run --package route-engine pytest packages/route-engine/tests --cov=route_engine
```

## 示例

```
路线：云雀优选超市 → 巨幕星云影院
  1. [walk]     云雀优选超市(B1) → 走廊点(600,560)(B1)   13.5m  11.2s
  ...
  4. [elevator] B1 直梯(B1) → F1 直梯(F1)                  5.2m  60.0s
  ...
合计：173.9 米 / 256.2 秒（约 4 分 16 秒，含垂直交通惩罚）
```

## 如何摘出复用到其他项目

纯函数核 `graph.py` 零 DB 依赖（输入 dataclass 行），networkx 之上只有 ~120 行：A* + 可采纳启发（直线距离/最高速度）+ 无障碍过滤 + 业务错误码。换场景只需改 seed 的图生成规则；若要接入地理坐标，把启发函数的欧氏距离换 haversine 即可。
