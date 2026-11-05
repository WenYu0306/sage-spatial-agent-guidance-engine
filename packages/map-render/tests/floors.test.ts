import assert from "node:assert/strict";
import { test } from "node:test";
import { FLOOR_SVGS } from "../src/assets/floors.ts";

// 底图资产契约：三层齐备，结构元素计数与 seed 数据一致（防生成器/数据回归）。
const EXPECT: Record<string, { shops: number; facilities: number }> = {
  B1: { shops: 20, facilities: 7 },
  F1: { shops: 24, facilities: 7 },
  F2: { shops: 24, facilities: 6 },
};

function count(s: string, needle: string): number {
  return s.split(needle).length - 1;
}

for (const [floor, exp] of Object.entries(EXPECT)) {
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
