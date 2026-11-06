import assert from "node:assert/strict";
import { test } from "node:test";
import { navTo, parseHash } from "../src/lib/router.ts";
import { anonymousId } from "../src/lib/guest.ts";

test("parseHash：/m/route 落地、poi 详情、缺省搜索页", () => {
  assert.deepEqual(parseHash("#/m/route/301"), { page: "route", id: 301 });
  assert.deepEqual(parseHash("#/route/9"), { page: "route", id: 9 });
  assert.deepEqual(parseHash("#/poi/12"), { page: "poi", id: 12 });
  assert.deepEqual(parseHash("#/coupons"), { page: "coupons" });
  assert.deepEqual(parseHash("#/chat"), { page: "chat" });
  assert.deepEqual(parseHash(""), { page: "search" });
  assert.deepEqual(parseHash("#/m/route/abc"), { page: "search" }, "非法 id 落搜索页");
});

test("navTo：与 parseHash 互逆", () => {
  assert.deepEqual(parseHash(navTo({ page: "route", id: 5 })), { page: "route", id: 5 });
  assert.deepEqual(parseHash(navTo({ page: "poi", id: 7 })), { page: "poi", id: 7 });
});

test("anonymousId：同环境复用同一标识", () => {
  assert.equal(anonymousId(), anonymousId());
  assert.notEqual(anonymousId(), "");
});

test("U1 公网接力：/m/route/:id 路径形式落地到路线页（QR 无 hash）", async () => {
  const { parseLanding } = await import("../src/lib/router.ts");
  assert.deepEqual(parseLanding("/m/route/7", ""), { page: "route", id: 7 });
  assert.deepEqual(parseLanding("/", "#/m/route/7"), { page: "route", id: 7 });
  assert.deepEqual(parseLanding("/", "#/search"), { page: "search" });
  assert.deepEqual(parseLanding("/m/route/7", "#/coupons"), { page: "coupons" }, "hash 优先于路径");
});
