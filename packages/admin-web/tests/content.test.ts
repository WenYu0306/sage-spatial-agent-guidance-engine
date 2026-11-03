/** B3 纯逻辑：活动动作矩阵（镜像 M8 ACT_TARGET_ROLES）与券余量语气。 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { availableActActions, remainingTone } from "../src/lib/actActions.ts";

test("draft 活动仅可提交 pending", () => {
  assert.deepEqual(availableActActions("draft", ["venue_editor"]).map((a) => a.target), ["pending"]);
  assert.deepEqual(availableActActions("draft", ["merchant"]).map((a) => a.target), ["pending"]);
});

test("pending→active 仅 admin；editor 可驳回", () => {
  assert.deepEqual(availableActActions("pending", ["venue_admin"]).map((a) => a.target),
    ["active", "draft"]);
  assert.deepEqual(availableActActions("pending", ["venue_editor"]).map((a) => a.target), ["draft"]);
});

test("active→ended、ended→archived 均 admin", () => {
  assert.deepEqual(availableActActions("active", ["venue_editor"]), []);
  assert.deepEqual(availableActActions("ended", ["venue_admin"]).map((a) => a.target), ["archived"]);
  assert.deepEqual(availableActActions("archived", ["venue_admin"]), []);
});

test("remainingTone：紧张红/充足绿", () => {
  assert.equal(remainingTone(0), "red");
  assert.equal(remainingTone(2), "amber");
  assert.equal(remainingTone(50), "green");
});
