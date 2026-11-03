/** PoiPoint ↔ pois_*.yaml 行互转（格式与 deploy/seed/data/pois_*.yaml 完全一致，纯函数）。 */

import type { PoiPoint } from "./types.ts";

const DEFAULT_HOURS = "10:00-22:00";

export function toYamlLine(p: PoiPoint): string {
  const parts = [
    `name: ${p.name}`,
    `category: ${p.category}`,
    `x: ${p.x}`,
    `y: ${p.y}`,
    `hours: "${p.hours}"`,
  ];
  if (p.tags.length > 0) parts.push(`tags: [${p.tags.join(", ")}]`);
  if (p.hot !== undefined) parts.push(`hot: ${p.hot}`);
  if (p.weight !== undefined && p.weight !== 1.0) parts.push(`weight: ${p.weight}`);
  return `- {${parts.join(", ")}}`;
}

export function toYamlDoc(points: PoiPoint[], floor: string): string {
  const head = [
    `# PoiPicker 导出（${floor} 层）`,
    `# 用法：替换/合并到 deploy/seed/data/pois_${floor.toLowerCase()}.yaml 的 pois: 列表，然后 make seed`,
  ];
  return [...head, ...points.map(toYamlLine), ""].join("\n");
}

/** 括号感知的顶层逗号切分（tags: [a, b] 内的逗号不切）。 */
export function splitTopLevel(s: string): string[] {
  const out: string[] = [];
  let depth = 0;
  let cur = "";
  for (const ch of s) {
    if (ch === "[") depth += 1;
    if (ch === "]") depth -= 1;
    if (ch === "," && depth === 0) {
      out.push(cur.trim());
      cur = "";
      continue;
    }
    cur += ch;
  }
  if (cur.trim()) out.push(cur.trim());
  return out;
}

export function parseYamlLine(line: string, floor: string): PoiPoint | null {
  const m = line.trim().match(/^- \{(.+)\}$/);
  if (!m) return null;
  const kv = new Map<string, string>();
  for (const pair of splitTopLevel(m[1])) {
    const i = pair.indexOf(":");
    if (i > 0) kv.set(pair.slice(0, i).trim(), pair.slice(i + 1).trim());
  }
  const tags = (kv.get("tags") ?? "")
    .replace(/^\[/, "")
    .replace(/\]$/, "")
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean);
  const point: PoiPoint = {
    name: kv.get("name") ?? "",
    category: kv.get("category") ?? "",
    floor: kv.get("floor") ?? floor,
    x: Number(kv.get("x")),
    y: Number(kv.get("y")),
    hours: (kv.get("hours") ?? `"${DEFAULT_HOURS}"`).replaceAll('"', ""),
    tags,
  };
  if (kv.has("hot")) point.hot = Number(kv.get("hot"));
  if (kv.has("weight")) point.weight = Number(kv.get("weight"));
  return point;
}

export function parseYamlDoc(text: string, floor: string): PoiPoint[] {
  return text
    .split("\n")
    .map((line) => parseYamlLine(line, floor))
    .filter((p): p is PoiPoint => p !== null && p.name !== "" && Number.isFinite(p.x));
}
