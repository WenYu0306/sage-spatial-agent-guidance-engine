# M1 platform-core — 多租户 / RBAC / 配置 / 日志 trace / 认证（L0 基础层）

## 做什么

全仓共享地基（L0，各包可 import，见 D-018）：
- **config**：`Settings.from_env()`，全部配置读环境变量（DATABASE_URL/REDIS_URL/SVC_*/JWT_SECRET）
- **trace / logging**：`new_trace_id()`（`tr_`+12hex）+ JSON 结构化日志（含 trace_id）
- **llm**：自建 `LLMProvider`（OpenAI 兼容双端点 chat/embedding、每日限额、Mock 降级，M5 引入）
- **auth**：bcrypt cost12 口令、JWT 签发/验证（access 2h 携带角色与范围，refresh 7d 最小化轮换）、
  登录失败锁定（`LOCKOUT_MAX_ATTEMPTS`/`LOCKOUT_SECONDS`）、登出黑名单（Redis 带 TTL，降级进程内存）
- **auth_router**：`AuthRuntime`（FastAPI 依赖工厂）+ `/api/v1/auth/login|refresh` 路由 +
  `install_error_handlers`。越权一律 403/`1003`（写 operation_logs）、无凭证 401/`1001`；
  merchant 额外注入 `merchant_id` 过滤（PRD 2.2 数据范围强制规则）

多租户原则贯穿：token 携带 `tenant_id`/`venue_id`/`merchant_id`，服务层用 `ctx.ensure_venue()`
/`ctx.ensure_merchant()` 强制数据范围，禁止依赖前端传参决定范围。

## 对外接口

- `POST /api/v1/auth/login`：body `{tenant_code, username, password}` → 200 `{access_token,
  refresh_token, token_type, expires_in, display_name, roles, venue_id}`；失败 401+`1001`
  （统一话术防用户枚举）
- `POST /api/v1/auth/refresh`：body `{refresh_token}` → 新 token 对（按库重查角色，旧 refresh
  jti 进黑名单轮换作废）；失败 401+`1001`
- `runtime.dependency(*roles)`：FastAPI 依赖，保护任意端点；`AuthContext.ensure_venue(id)` /
  `.ensure_merchant(poi_id)` 校验数据范围
- 契约：`packages/api-contract/openapi/auth.yaml`

## 如何单独运行

```bash
cd packages/platform-core && make demo
# 前置：根目录 make migrate && make seed（.env 里 SEED_DEMO_ADMIN_PASSWORD、JWT_SECRET 已设）
```

## 示例（make demo 真实输出摘要）

```
demo_admin     → roles=['venue_admin'] venue_id=1 expires_in=7200s
editor 调账号管理    → HTTP 403 {'error_code': 1003, 'message': '你没有该操作的权限'}
merchant 改别家门店  → HTTP 403 {'error_code': 1003, 'message': '你没有该门店的操作权限'}
无凭证访问后台       → HTTP 401 {'error_code': 1001, 'message': '缺少 Bearer 凭证'}
错误口令 → 401/1001（第 5 次起锁定 900s）；旧 refresh 重放 → 401 'token 已登出'
```

M8 内容服务建成后，业务端点直接复用 `Depends(runtime.dependency(...))`，无需改造。

## 如何摘出复用到其他项目

- **复制**：`platform_core/auth.py` + `auth_router.py`（约 420 行，零业务词）+ `openapi/auth.yaml`
- **改配置**：`.env` 提供 `JWT_SECRET`（≥32 字节）、`DATABASE_URL`、`REDIS_URL`（可选，无 Redis
  自动内存黑名单）；角色码/锁定阈值按你的业务改
- **跑验证**：`pytest tests/test_auth.py tests/test_rbac_api.py`（34 条含越权五连）
- **适用**：任何多租户 SaaS 的后台鉴权层——角色绑定数据范围（venue/merchant 两级）的设计
  对"平台-租户-子资源"结构通用；内核纯净性（无业务词）由 import-linter 契约保护
