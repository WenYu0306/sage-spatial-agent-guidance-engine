import assert from "node:assert/strict";
import { test } from "node:test";

import { inBounds, snap } from "../src/lib/svgCoords.ts";

test("snap rounds to grid step", () => {
  assert.equal(snap(149.6), 150);
  assert.equal(snap(150.4), 150);
  assert.equal(snap(151.0), 151);
  assert.equal(snap(149.6, 10), 150);
});

test("inBounds enforces viewBox 1200x800 with margin", () => {
  assert.ok(inBounds(1, 1, 1200, 800));
  assert.ok(inBounds(1199, 799, 1200, 800));
  assert.equal(inBounds(0, 400, 1200, 800), false);
  assert.equal(inBounds(1200, 400, 1200, 800), false);
  assert.equal(inBounds(600, 0, 1200, 800), false);
  assert.equal(inBounds(600, 800, 1200, 800), false);
  assert.equal(inBounds(-5, 400, 1200, 800), false);
});
