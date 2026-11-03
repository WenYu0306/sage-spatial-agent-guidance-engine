/** 点位列表纯操作：同名覆盖、异名追加（录入工具的 upsert 语义）。 */

import type { PoiPoint } from "./types.ts";

export function upsertPoint(points: PoiPoint[], p: PoiPoint): PoiPoint[] {
  const idx = points.findIndex((q) => q.name === p.name);
  if (idx === -1) return [...points, p];
  const next = [...points];
  next[idx] = p;
  return next;
}
