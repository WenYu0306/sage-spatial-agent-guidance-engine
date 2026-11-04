# M4 map-render — 分层 SVG 渲染与点位工具

## 做什么

分层 SVG 地图渲染（viewBox 1200×800 平面坐标）、缩放拖动（react-zoom-pan-pinch）、楼层切换、路线绘制（消费与 M3 `RouteResult` 同构的分段数据）、**PoiPicker 点位标注工具**（F-05）。

## 对外接口

- `src/lib/svgCoords.ts`：`clientToSvg`（getScreenCTM 逆变换，屏坐标→viewBox 坐标）/ `snap` / `inBounds`
- `src/lib/poiExport.ts`：`toYamlLine/toYamlDoc/parseYamlDoc` — 与 `deploy/seed/data/pois_*.yaml` **完全同格式**的导出/导入
- `src/lib/routeDraw.ts`：`floorPolylines(route, floor)` — 分段路线按楼层拆画线/换乘标记
- 组件：`FloorPlan`（真实底图+标记层+overlay 插槽）、`MapStage`（缩放拖动）、`PoiPicker`（index.html）、`RouteApp`（route.html）
- `src/assets/floors.ts`：内嵌三层真实底图（**生成物勿手改**）——由 `python3 scripts/gen_floor_maps.py` 从 `deploy/seed/data` 单一数据源生成，同步输出 deploy/maps/{b1,f1,f2}.svg

## 如何单独运行

```bash
pnpm install
pnpm --filter @sage/map-render demo   # http://localhost:5190（PoiPicker）
                                       # http://localhost:5190/route.html（路线渲染）
pnpm --filter @sage/map-render test    # node:test 22 个（纯函数 + 底图资产契约）
pnpm --filter @sage/map-render exec tsc --noEmit
```

## 示例（PoiPicker 工作流）

1. 打开 `localhost:5190`，选楼层（B1/F1/F2）；
2. 在地图上**点击**拾点（红圈=草稿点，坐标自动取整到 1 SVG 单位）；
3. 右侧表单填名称/分类/营业时间/标签/热度 →「加入列表」；加入后坐标保留，改名/点新位置可连续录入（同名覆盖）；
4. 「复制 YAML」一键进剪贴板（或「查看」展开全文），**直接贴回** `deploy/seed/data/pois_<层>.yaml` 的 `pois:` 列表 → `make seed` 入库；
5. 微调已有点位：把现有 YAML 行粘进「导入」框 → 移动/删除 → 再导出。

## 如何摘出复用到其他项目

坐标换算/导出解析/画线拆分全是纯函数（无 React 依赖），换场景只改：底图由 `scripts/gen_floor_maps.py` 的布局模板参数化重绘（改布局约定+重跑即可，店面图形自动随 seed 数据走）、CATEGORIES 字典、`deploy/seed` 对应数据格式。缩放拖动引擎 react-zoom-pan-pinch（MIT）独立可替换。
