import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

// favicon 404 防复发：入口 HTML 必须声明 icon（否则浏览器自动请求 /favicon.ico 必 404）
for (const f of ["index.html", "route.html"]) {
  test(`${f} declares an icon`, () => {
    const html = readFileSync(new URL(`../${f}`, import.meta.url), "utf-8");
    assert.match(html, /rel="icon"/);
  });
}
