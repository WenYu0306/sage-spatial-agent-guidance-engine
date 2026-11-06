/** U1-a 路线文案语义化：根除「走廊点(x,y)」机器话（三端共用助手）。 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  CORRIDOR_LABEL,
  describeSegment,
  fmtDistance,
  fmtDuration,
  friendlyLabel,
  routeTitle,
} from "../src/lib/routeCopy.ts";

const nodes = {
  1: { label: "云雀优选超市", floor: "B1" },
  2: { label: "沿走廊", floor: "B1" },
  3: { label: "沿走廊", floor: "F2" },
  4: { label: "巨幕星云影院", floor: "F2" },
};

test("friendlyLabel 把坐标兜底话术归一为「沿走廊」", () => {
  assert.equal(friendlyLabel("走廊点(600.00,260.00)"), CORRIDOR_LABEL);
  assert.equal(friendlyLabel("沿走廊"), CORRIDOR_LABEL);
  assert.equal(friendlyLabel("巨幕星云影院"), "巨幕星云影院");
  assert.equal(friendlyLabel(null), CORRIDOR_LABEL);
});

test("fmtDistance 取整、fmtDuration 人话化", () => {
  assert.equal(fmtDistance(113.31), "113 米");
  assert.equal(fmtDuration(45), "45 秒");
  assert.equal(fmtDuration(89), "89 秒");
  assert.equal(fmtDuration(150), "约 3 分钟");
  assert.equal(fmtDuration(262.59), "约 4 分钟");
});

test("describeSegment：步行到店 / 沿走廊 / 垂直交通三种话术", () => {
  assert.equal(
    describeSegment({ from_id: 1, to_id: 2, edge_type: "walk", distance_meter: 9.2, time_s: 8 }, nodes),
    "沿走廊步行 9 米",
  );
  assert.equal(
    describeSegment({ from_id: 3, to_id: 4, edge_type: "walk", distance_meter: 22.61, time_s: 19 }, nodes),
    "步行至 巨幕星云影院 · 23 米",
  );
  assert.equal(
    describeSegment({ from_id: 2, to_id: 3, edge_type: "elevator", distance_meter: 5.2, time_s: 60 }, nodes),
    "乘直梯 B1 → F2 · 5 米",
  );
  assert.equal(
    describeSegment({ from_id: 2, to_id: 3, edge_type: "escalator", distance_meter: 5.2, time_s: 15 }, nodes),
    "乘扶梯 B1 → F2 · 5 米",
  );
});

test("routeTitle：起点未知名显示「您附近」", () => {
  assert.equal(
    routeTitle("走廊点(600,260)", "巨幕星云影院", 113.31, 150),
    "您附近 → 巨幕星云影院 · 113 米 · 约 3 分钟",
  );
  assert.equal(
    routeTitle("云雀优选超市", "巨幕星云影院", 181.5, 262.59),
    "云雀优选超市 → 巨幕星云影院 · 182 米 · 约 4 分钟",
  );
});

test("describeSegment 兼容 from/to 与 from_id/to_id 两种载荷形状", () => {
  assert.equal(
    describeSegment({ from: 1, to: 2, edge_type: "walk", distance_meter: 9.2, time_s: 8 }, nodes),
    "沿走廊步行 9 米",
  );
});
