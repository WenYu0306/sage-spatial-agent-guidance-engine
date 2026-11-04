import assert from "node:assert/strict";
import { test } from "node:test";
import { carouselStep, nextRoute, toAdCards } from "../src/lib/kiosk.ts";
import { buildEvent } from "../src/lib/events.ts";
import { decodeJwtPayload } from "../src/lib/device.ts";

test("nextRoute：idle/ home 永远回首页，ask/route 各自跳转", () => {
  assert.equal(nextRoute("chat", "idle"), "home");
  assert.equal(nextRoute("route", "home"), "home");
  assert.equal(nextRoute("home", "ask"), "chat");
  assert.equal(nextRoute("chat", "route"), "route");
});

test("carouselStep：循环步进，空列表恒 0", () => {
  assert.equal(carouselStep(3, 0), 1);
  assert.equal(carouselStep(3, 2), 0);
  assert.equal(carouselStep(0, 5), 0);
});

test("toAdCards：活动/优惠券映射与空输入", () => {
  const cards = toAdCards(
    [{ id: 1, title: "周年庆", description: null }],
    [{ id: 2, title: "满减券", coupon_type: "fixed", threshold: 100, value: 20 }],
  );
  assert.deepEqual(cards, [
    { key: "a-1", kind: "activity", title: "周年庆", detail: "限时活动进行中" },
    { key: "c-2", kind: "coupon", title: "满减券", detail: "满 100 减 20" },
  ]);
  assert.deepEqual(toAdCards([], []), []);
});

test("buildEvent：uuid/时间戳/字段完整", () => {
  const e = buildEvent({ tenantId: 1, venueId: 2, eventType: "ad_impression",
                         deviceId: 3, payload: { x: 1 } });
  assert.equal(e.event_type, "ad_impression");
  assert.equal(e.actor_type, "device");
  assert.equal(e.device_id, 3);
  assert.ok(/^[0-9a-f-]{36}$/.test(e.event_id));
  assert.ok(!Number.isNaN(Date.parse(e.occurred_at)));
});

test("decodeJwtPayload：CJK 与 base64url 安全", () => {
  const payload = { sub: "1", display_name: "栖云广场" };
  const b64 = (s: string) => {
    const bytes = new TextEncoder().encode(s);
    let bin = "";
    for (const b of bytes) bin += String.fromCharCode(b);
    return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  };
  const token = `${b64('{"alg":"HS256"}')}.${b64(JSON.stringify(payload))}.sig`;
  assert.deepEqual(decodeJwtPayload(token), payload);
  assert.equal(decodeJwtPayload("garbage"), null);
});

test("createSSEParser：跨 chunk 事件帧与多 data 行", async () => {
  const { createSSEParser } = await import("../src/lib/sse.ts");
  const seen: Array<[string, string]> = [];
  const feed = createSSEParser((event, data) => seen.push([event, data]));
  feed('event: met');
  feed('a\ndata: {"session_id": 88}\n\nevent: delta\ndata: {"text": "你');
  feed('好"}\n\n');
  assert.deepEqual(seen, [
    ["meta", '{"session_id": 88}'],
    ["delta", '{"text": "你好"}'],
  ]);
});
