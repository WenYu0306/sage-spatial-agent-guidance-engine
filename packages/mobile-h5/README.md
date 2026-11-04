# M12 mobile-h5 — 手机导视 H5（扫码接力 / F-11）

## 做什么

顾客手机端（375-430px）：大屏二维码落地（#/m/route/:id，30 分钟有效）→ 路线详情（真底图画线+分段）；找店（关键词搜索 published POI）→ 店铺详情（7 天营业时间/标签/介绍/联系）；问一问（guest 匿名 SSE）；优惠领取（幂等键 coupon_id+anonymous_id）。PRD 825 降级四件套齐全。

## 对外接口

- 消费后端：`GET /api/v1/route/{id}`（2005 过期页）、`GET /pois`（guest+venue_id，仅 published）、`GET /pois/{id}`、`GET /coupons`、`POST /coupons/{id}/claim`、`POST /agent/chat`（SSE，X-Client: mobile，anonymous_id）
- `src/lib/router.ts`：`parseHash/navTo`（落地契约 /m/route/{id}，纯函数）
- `src/lib/guest.ts`：anonymous_id（localStorage UUID，PRD 2.3）
- 复用 `@sage/map-render`：FloorPlan/routeDraw/http（api/sse/events 三端共享）

## 如何单独运行

```bash
# 需要后端：content(8945)/agent(8941)/route(8942)；analytics(8946) 埋点可选
pnpm --filter @sage/mobile-h5 demo      # http://localhost:5194
pnpm --filter @sage/mobile-h5 test      # node:test 3 个（路由互逆/落地解析/游客标识）
pnpm --filter @sage/mobile-h5 exec tsc --noEmit
```

## 示例（扫码接力动线）

大屏生成二维码 → 手机扫码打开 `#/m/route/301` → 看路线图与分段 → 点「找店」搜咖啡 → 店铺详情 → 「优惠」领券（重复领取提示已领过）。

## 如何摘出复用到其他项目

落地页契约（router.ts 一处改 URL 规则）、guest 身份（guest.ts）、SSE/埋点/HTTP 全在 map-render 共享包；页面层替换数据源即可整体搬走。
