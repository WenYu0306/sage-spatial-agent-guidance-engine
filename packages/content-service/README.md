# M8 content-service — 内容与营销服务（US-012）

## 做什么

挂载 M1 认证（`/api/v1/auth/*` 登录入口在本服务）并提供 PRD 7.3 内容端点：
venues/floors/map-layer/categories 只读；POI CRUD+软删+发布状态机
（draft→pending→published/offline，非法跳转 409/4001，审核仅 venue_admin）；
活动状态机（draft→pending→active→ended/archived）；优惠券列表与领取
（幂等键 `coupon_id:anonymous_id`，库存原子扣减，售罄 4002，重放返回
既有券 duplicate=true）；知识文档 CRUD（内容更新版本自增）。
每条写操作与 403 越权均落 `operation_logs`。范围强制：token 携带
tenant/venue/merchant，服务层注入过滤（PRD 2.2），merchant 锚点语义见 D-021。

## 对外接口

- `/api/v1/auth/login|refresh`（M1 复用）
- `GET /api/v1/venues`、`GET /venues/{id}/floors`、`GET /floors/{id}/map-layer`、`GET /categories`
- `GET/POST/PATCH/DELETE /api/v1/pois`、`GET /pois/{id}`、`POST /pois/{id}/publish`
- `GET/POST/PATCH /api/v1/activities`、`POST /activities/{id}/publish`
- `GET /api/v1/coupons`、`POST /coupons/{id}/claim`（guest 无需登录，anonymous_id 必填）
- `GET/POST/PATCH/DELETE /api/v1/knowledge-documents`
- 错误码：401/1001、403/1003、409/4001（状态）、4002（已领完）
- `python -m uvicorn content_service.app:make_app --factory --port 8945`

## 如何单独运行

```bash
cd packages/content-service && make demo
# 前置：根目录 make migrate && make seed（.env 需 JWT_SECRET/SEED_DEMO_ADMIN_PASSWORD）
```

## 示例（make demo 真实输出摘要）

```
demo_admin 登录 → roles=['venue_admin'] venue_id=1
POI 列表（keyword=火锅）→ 3 条（分页 total=3）
新建 POI → draft → 提交 pending → editor 审核被拒 403/1003 → admin 发布 published
领券：首领 ok → 同 anonymous 重放 duplicate=true（库存不重复扣）→ 第三人领 → 4002 售罄
```

## 如何摘出复用到其他项目

- **复制**：`content_service/`（app.py 约 600 行）+ 依赖 platform_core 的 auth 两件
- **改配置**：状态机表（POI_TRANSITIONS/ACT_TRANSITIONS 与角色门）按你的业务流转改；
  merchant 锚点若有多门店商户，升级为独立商户表并改 `_load_poi_for_write`
- **跑验证**：`pytest tests/ -q`（25 条：范围注入/状态机/幂等/越权矩阵）
- **适用**：任何多租户内容后台（门店/网点/展位管理），状态机+幂等+范围注入
  三件套与业务无关，可直接平移
