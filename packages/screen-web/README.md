# M11 screen-web — 商场导视大屏（kiosk）

## 做什么

顾客触屏大屏的 H5 全屏页（F-17）：首页（欢迎语/快捷入口/闲置轮播广告）→ AI 问答（SSE 流式+结果卡）→ 路线展示（真实底图画线）→ 二维码接力到手机（F-11）+ 无障碍模式。设备以 device 角色登录（D-028），心跳/埋点齐全（device_active/ad_impression/ad_click/route_handover）。

## 对外接口

- 消费后端：`POST /api/v1/agent/chat`（SSE：meta/delta/card/citations/route/done）、`GET /api/v1/devices/me`（设备自读：场地名/营业时间/楼层/坐标）、`POST /api/v1/devices/{id}/heartbeat`、`POST /api/v1/events`（直报）、`GET /api/v1/activities|coupons?status=active`（轮播数据）
- `src/lib/device.ts`：env 凭据登录 → JWT claims → 设备身份（tenant/venue/device id + 场地配置），401 自动重登
- `src/lib/sse.ts`：SSE 帧解析状态机（跨 chunk 安全，纯函数）
- `src/lib/events.ts`：`buildEvent/trackEvents`（event_id=UUID 幂等，`{events:[...]}` 包裹体）
- `src/lib/kiosk.ts`：路由状态机（90s 闲置回首页）/轮播步进/广告卡映射（纯函数）
- `src/lib/route.ts`：M5 路线载荷 → map-render routeDraw 适配器；`qrTarget`（M12 契约 `/m/route/{route_id}`）

## 如何单独运行

```bash
# 需要后端：content(8945)/agent(8941)/analytics(8946)/route(8942)/recommender(8944)
VITE_SCREEN_USERNAME=screen-f1-01 VITE_SCREEN_PASSWORD=<SEED_DEMO_ADMIN_PASSWORD> \
  pnpm --filter @sage/screen-web demo        # http://localhost:5192
pnpm --filter @sage/screen-web test          # node:test 8 个纯函数测试
pnpm --filter @sage/screen-web exec tsc --noEmit
```

## 示例（顾客动线）

首页点「卫生间在哪」→ 问答页自动发送 → 流式回答 + 最近卫生间卡片 → 点「查看路线」→ 真实底图画线（步行/直梯分色、换乘徽标、楼层切换）→ 点「发到手机」→ 二维码（30 分钟有效，M12 扫码接力）→ 90 秒无操作自动回首页轮播。

## 如何摘出复用到其他项目

换场景只改三处：`kiosk.ts` 的快捷入口/`Home.tsx` 轮播数据源（换 campaigns 端点）、`lib/route.ts` 的落地页契约（换移动端路由）、`styles.css` 主题色。设备会话（device.ts）、SSE 解析器、埋点直报、kiosk 状态机均为场景无关组件，可直接搬。
