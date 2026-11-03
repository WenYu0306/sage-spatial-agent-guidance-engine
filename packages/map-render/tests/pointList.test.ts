import assert from "node:assert/strict";
import { test } from "node:test";

import { upsertPoint } from "../src/lib/pointList.ts";
import type { PoiPoint } from "../src/lib/types.ts";

const a: PoiPoint = { name: "A", category: "gym", floor: "F1", x: 1, y: 2, hours: "10:00-22:00", tags: [] };
const b: PoiPoint = { name: "B", category: "cafe", floor: "F1", x: 3, y: 4, hours: "10:00-22:00", tags: [] };
const a2: PoiPoint = { ...a, x: 9, y: 9 };

test("upsertPoint appends unknown names in order", () => {
  assert.deepEqual(upsertPoint([], a), [a]);
  assert.deepEqual(
    upsertPoint([a], b).map((p) => p.name),
    ["A", "B"],
  );
});

test("upsertPoint replaces same-name point in place", () => {
  const next = upsertPoint([a, b], a2);
  assert.equal(next.length, 2);
  assert.deepEqual(next[0], a2);
  assert.deepEqual(next[1], b);
});

test("upsertPoint does not mutate input", () => {
  const src = [a];
  upsertPoint(src, b);
  assert.equal(src.length, 1);
});
