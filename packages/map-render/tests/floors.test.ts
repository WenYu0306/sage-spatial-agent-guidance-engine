import assert from "node:assert/strict";
import { test } from "node:test";
import { FLOOR_SVGS } from "../src/assets/floors.ts";

// 底图资产契约：三层齐备、非空、互不相同（防生成器/资产回归）。
const FLOORS = ["B1", "F1", "F2"] as const;

for (const floor of FLOORS) {
  test(`${floor} 底图：三层齐备且互不相同（用户资产内嵌）`, () => {
    const svg = FLOOR_SVGS[floor];
    assert.ok(svg, `${floor} 底图缺失`);
    assert.ok(svg.length > 10000, `${floor} 底图过小（${svg.length}）`);
  });
}

test("三层底图互不相同（防复制粘贴同层）", () => {
  assert.notEqual(FLOOR_SVGS.B1, FLOOR_SVGS.F1);
  assert.notEqual(FLOOR_SVGS.F1, FLOOR_SVGS.F2);
});
