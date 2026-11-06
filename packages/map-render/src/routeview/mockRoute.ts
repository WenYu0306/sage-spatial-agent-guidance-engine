/** 内置 mock：与 route_engine.demo（云雀优选超市 → 巨幕星云影院）真实输出同构。 */

import type { RouteData } from "../lib/routeDraw.ts";

export const MOCK_ROUTE: RouteData = {
  start_label: "云雀优选超市",
  goal_label: "巨幕星云影院",
  total_distance_meter: 173.9,
  total_time_s: 256.2,
  nodes: {
    1: { id: 1, x: 600, y: 650, floor: "B1", label: "云雀优选超市" },
    2: { id: 2, x: 600, y: 560, floor: "B1", label: "沿走廊" },
    3: { id: 3, x: 600, y: 260, floor: "B1", label: "沿走廊" },
    4: { id: 4, x: 600, y: 200, floor: "B1", label: "B1 直梯" },
    5: { id: 5, x: 600, y: 200, floor: "F1", label: "F1 直梯" },
    6: { id: 6, x: 600, y: 200, floor: "F2", label: "F2 直梯" },
    7: { id: 7, x: 600, y: 260, floor: "F2", label: "沿走廊" },
    8: { id: 8, x: 1050, y: 260, floor: "F2", label: "沿走廊" },
    9: { id: 9, x: 1050, y: 130, floor: "F2", label: "巨幕星云影院" },
  },
  segments: [
    { from: 1, to: 2, edge_type: "walk", distance_meter: 13.5, time_s: 11.2 },
    { from: 2, to: 3, edge_type: "walk", distance_meter: 45.0, time_s: 37.5 },
    { from: 3, to: 4, edge_type: "walk", distance_meter: 9.0, time_s: 7.5 },
    { from: 4, to: 5, edge_type: "elevator", distance_meter: 5.2, time_s: 60.0 },
    { from: 5, to: 6, edge_type: "elevator", distance_meter: 5.2, time_s: 60.0 },
    { from: 6, to: 7, edge_type: "walk", distance_meter: 9.0, time_s: 7.5 },
    { from: 7, to: 8, edge_type: "walk", distance_meter: 67.5, time_s: 56.2 },
    { from: 8, to: 9, edge_type: "walk", distance_meter: 19.5, time_s: 16.2 },
  ],
};
