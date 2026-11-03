import assert from "node:assert/strict";
import { test } from "node:test";

import { floorPolylines } from "../src/lib/routeDraw.ts";
import { MOCK_ROUTE } from "../src/routeview/mockRoute.ts";

test("B1 floor has 3 walk lines and 1 elevator badge", () => {
  const { lines, badges } = floorPolylines(MOCK_ROUTE, "B1");
  assert.equal(lines.length, 3);
  assert.equal(badges.length, 1);
  assert.equal(badges[0].edge_type, "elevator");
  assert.equal(badges[0].to_floor, "F1");
});

test("F1 transit floor has no walk lines but 2 elevator badges", () => {
  const { lines, badges } = floorPolylines(MOCK_ROUTE, "F1");
  assert.equal(lines.length, 0);
  assert.equal(badges.length, 2);
});

test("F2 floor has 3 walk lines and 1 arrival badge", () => {
  const { lines, badges } = floorPolylines(MOCK_ROUTE, "F2");
  assert.equal(lines.length, 3);
  assert.equal(badges.length, 1);
  assert.equal(badges[0].to_floor, "F1");
});

test("line endpoints match node coordinates", () => {
  const { lines } = floorPolylines(MOCK_ROUTE, "B1");
  const first = lines[0];
  assert.deepEqual(
    [first.x1, first.y1, first.x2, first.y2],
    [600, 650, 600, 560],
  );
});
