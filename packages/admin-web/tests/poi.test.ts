/** B2 纯逻辑：发布动作矩阵（与 M8 POI_TARGET_ROLES 镜像）与列表过滤参数。 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { availableActions, buildPoiQuery } from "../src/lib/poiActions.ts";

test("draft 态：editor/merchant 可提交，无审核按钮", () => {
  const acts = availableActions("draft", ["venue_editor"]);
  assert.deepEqual(acts.map((a) => a.target), ["pending"]);
  assert.deepEqual(availableActions("draft", ["merchant"]).map((a) => a.target), ["pending"]);
});

test("pending 态：仅 admin 见审核通过；editor 可驳回", () => {
  assert.deepEqual(availableActions("pending", ["venue_admin"]).map((a) => a.target),
    ["published", "draft"]);
  assert.deepEqual(availableActions("pending", ["venue_editor"]).map((a) => a.target),
    ["draft"], "editor 不能审核通过");
  assert.deepEqual(availableActions("pending", ["merchant"]), [], "merchant 无 pending 态动作");
});

test("published→offline 仅 admin；offline→draft editor 可回", () => {
  assert.deepEqual(availableActions("published", ["venue_admin"]).map((a) => a.target), ["offline"]);
  assert.deepEqual(availableActions("published", ["venue_editor"]), []);
  assert.deepEqual(availableActions("offline", ["venue_editor"]).map((a) => a.target), ["draft"]);
});

test("buildPoiQuery 省略空值并编码", () => {
  const q = buildPoiQuery({ keyword: "火锅", page: 2, pageSize: 10, category: "", floorId: null, openNow: false, status: "" });
  assert.equal(q, "keyword=%E7%81%AB%E9%94%85&page=2&page_size=10");
  assert.equal(buildPoiQuery({ page: 1, pageSize: 20 }), "page=1&page_size=20");
  assert.equal(buildPoiQuery({ openNow: true, page: 1, pageSize: 20 }), "open_now=true&page=1&page_size=20");
});
