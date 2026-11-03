/** B1 纯逻辑测试：JWT 解码与角色、API 错误映射、表单校验（node:test + TS 直跑）。 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { decodeJwtPayload, isRoleAllowed, tokenStore } from "../src/lib/auth.ts";
import { ApiError, mapResponse } from "../src/lib/api.ts";
import { validatePoiForm, validateLoginForm } from "../src/lib/validate.ts";

// HS256 无签名校验的 payload（demo 用途：仅解码展示，鉴权在服务端）
const TOKEN =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9." +
  Buffer.from(JSON.stringify({
    sub: "7", tenant_id: 1, roles: ["venue_admin"], venue_id: 1,
  })).toString("base64url") +
  ".sig";

test("decodeJwtPayload 解出角色与范围", () => {
  const payload = decodeJwtPayload(TOKEN);
  assert.equal(payload?.roles[0], "venue_admin");
  assert.equal(payload?.tenant_id, 1);
  assert.equal(decodeJwtPayload("garbage"), null);
});

test("tokenStore 存取与清除（存储可注入，node 无 localStorage）", () => {
  const mem = new Map<string, string>();
  const fake = { getItem: (k: string) => mem.get(k) ?? null, setItem: (k: string, v: string) => void mem.set(k, v), removeItem: (k: string) => void mem.delete(k) };
  const store = tokenStore(fake);
  store.set(TOKEN);
  assert.equal(store.get(), TOKEN);
  store.clear();
  assert.equal(store.get(), null);
});

test("isRoleAllowed：无声明角色放行只读，写角色须命中", () => {
  assert.equal(isRoleAllowed(["venue_admin"], ["platform_admin", "venue_admin"]), true);
  assert.equal(isRoleAllowed(["venue_editor"], ["platform_admin", "venue_admin"]), false);
});

test("mapResponse：业务错误包络 → ApiError", async () => {
  const bad = new Response(JSON.stringify({ error_code: 1003, message: "无权限" }), { status: 403 });
  await assert.rejects(() => mapResponse(bad), (e: ApiError) => e.error_code === 1003);
  const ok = new Response(JSON.stringify({ items: [] }), { status: 200 });
  const body = await mapResponse<{ items: string[] }>(ok);
  assert.deepEqual(body.items, []);
});

test("validateLoginForm：必填校验", () => {
  assert.ok(validateLoginForm("", "x").length > 0);
  assert.deepEqual(validateLoginForm("u", "p"), []);
});

test("validatePoiForm：名称/坐标/营业时段", () => {
  const errs = validatePoiForm({ name: "", position_x: NaN, position_y: 1, business_hours: { mon: ["25:00-26:00"] } });
  assert.ok(errs.some((e) => e.field === "name"));
  assert.ok(errs.some((e) => e.field === "position_x"));
  assert.ok(errs.some((e) => e.field === "business_hours"));
  assert.deepEqual(
    validatePoiForm({ name: "茶餐厅", position_x: 10, position_y: 20, business_hours: { mon: ["10:00-22:00"] } }),
    [],
  );
});
