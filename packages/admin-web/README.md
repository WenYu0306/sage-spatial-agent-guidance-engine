# M10 admin-web — 商场运营后台（US-013）

## 做什么

12 页运营后台：登录（对接 M1 auth）、场地列表、POI 管理（组合过滤/编辑/
发布状态机按钮/坐标拾取）、活动管理（状态机+新建）、优惠管理（余量）、
知识内容管理（版本自增）、推荐权重（只读，F-16 冻结）、设备列表、
账号与角色（新建/禁用）、数据看板（M9 未接入的规范空态）。
每个数据请求五态齐全（加载/失败重试/空/无权限提示/toast）。
栈：React 19 + Vite 7 + Tailwind v4 + TanStack Query；自绘 shadcn 风格
复制式组件（D-023，无 radix）；hash 路由自写（无 router 框架）。

## 对外接口（消费方）

- M8 content-service（:8945，vite 代理 `/api`）：auth/venues/floors/pois/
  activities/coupons/knowledge-documents/users/devices
- M7 recommender（:8944，代理 `/recommend`）：权重只读
- 动作矩阵（发布/上线按钮显隐）在 src/lib/poiActions.ts、actActions.ts，
  与后端角色表严格镜像（node:test 锁定）

## 如何单独运行

```bash
cd packages/admin-web && pnpm install && pnpm demo   # http://localhost:5191
# 前置：content-service 8945（make demo 或 uvicorn content_service.app:make_app --factory --port 8945）
# 登录：demo_admin / $SEED_DEMO_ADMIN_PASSWORD
```

## 示例

登录 → 场地列表 → POI 管理筛选"火锅" → 编辑弹窗底图拾点保存 →
发布状态机（提交/审核/下架按角色显隐）→ 活动上线 → 知识编辑版本+1。
改营业时间后 `pois?open_now=true` 与 M5 AI 回答同步变化（US-013 数据链路）。

## 如何摘出复用到其他项目

- **复制**：src/lib（api 客户端/守卫/校验）+ src/components/ui.tsx（五态基件）
- **改配置**：vite 代理目标；动作矩阵与你的后端角色表对齐；FACTORS_ZH 等字典换文案
- **跑验证**：pnpm test（node:test 纯逻辑 14 条）+ tsc --noEmit + pnpm build
- **适用**：任何多租户内容后台；五态基件与声明式守卫模式直接平移
