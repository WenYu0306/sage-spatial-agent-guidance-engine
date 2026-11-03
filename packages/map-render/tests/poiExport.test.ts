import assert from "node:assert/strict";
import { test } from "node:test";

import { parseYamlDoc, parseYamlLine, splitTopLevel, toYamlDoc, toYamlLine } from "../src/lib/poiExport.ts";
import type { PoiPoint } from "../src/lib/types.ts";

const sample: PoiPoint = {
  name: "测试店铺",
  category: "hotpot",
  floor: "F2",
  x: 150,
  y: 180,
  hours: "10:30-21:30",
  tags: ["火锅", "聚餐"],
  hot: 85,
};

test("toYamlLine matches seed pois_*.yaml format", () => {
  assert.equal(
    toYamlLine(sample),
    '- {name: 测试店铺, category: hotpot, x: 150, y: 180, hours: "10:30-21:30", tags: [火锅, 聚餐], hot: 85}',
  );
});

test("toYamlLine omits default weight and empty tags", () => {
  const p = { ...sample, tags: [], weight: 1.0, hot: undefined };
  const line = toYamlLine(p);
  assert.equal(line, '- {name: 测试店铺, category: hotpot, x: 150, y: 180, hours: "10:30-21:30"}');
});

test("splitTopLevel keeps brackets intact", () => {
  assert.deepEqual(
    splitTopLevel('name: X, tags: [a, b], hours: "10:00-22:00"'),
    ['name: X', 'tags: [a, b]', 'hours: "10:00-22:00"'],
  );
});

test("parseYamlLine round-trips with toYamlLine", () => {
  const parsed = parseYamlLine(toYamlLine(sample), "F2");
  assert.deepEqual(parsed, sample);
});

test("parseYamlLine defaults weight to undefined and adds floor", () => {
  const parsed = parseYamlLine('- {name: A, category: gym, x: 5, y: 6, hours: "09:00-21:00"}', "B1");
  assert.equal(parsed?.floor, "B1");
  assert.equal(parsed?.weight, undefined);
  assert.equal(parsed?.hot, undefined);
});

test("toYamlDoc has header and floor note", () => {
  const doc = toYamlDoc([sample], "F2");
  assert.ok(doc.includes("# PoiPicker 导出（F2 层）"));
  assert.ok(doc.includes("pois_f2.yaml"));
  assert.ok(doc.includes(toYamlLine(sample)));
});

test("parseYamlDoc skips non-poi lines", () => {
  const doc = "# 注释\nfloor: F1\npois:\n" + toYamlLine(sample) + "\ngarbage line\n";
  const parsed = parseYamlDoc(doc, "F1");
  assert.equal(parsed.length, 1);
  assert.equal(parsed[0].name, "测试店铺");
});
