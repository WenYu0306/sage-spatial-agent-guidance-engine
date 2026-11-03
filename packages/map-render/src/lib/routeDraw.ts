/** M3 分段路线 → 各楼层画线/换乘标记（纯函数，渲染层与数据解耦）。 */

export interface RouteNode {
  id: number;
  x: number;
  y: number;
  floor: string; // B1/F1/F2
  label: string;
}

export interface RouteSegment {
  from: number;
  to: number;
  edge_type: string;
  distance_meter: number;
  time_s: number;
}

export interface RouteData {
  start_label: string;
  goal_label: string;
  total_distance_meter: number;
  total_time_s: number;
  nodes: Record<number, RouteNode>;
  segments: RouteSegment[];
}

export interface FloorLine {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  edge_type: string;
  seconds: number;
  meters: number;
}

export interface FloorBadge {
  x: number;
  y: number;
  edge_type: string;
  to_floor: string;
  seconds: number;
}

/** 给定楼层：walk 段两端都在该层 → 画线；垂直段 → 在该层端点画换乘标记。 */
export function floorPolylines(
  route: RouteData,
  floor: string,
): { lines: FloorLine[]; badges: FloorBadge[] } {
  const lines: FloorLine[] = [];
  const badges: FloorBadge[] = [];
  for (const s of route.segments) {
    const a = route.nodes[s.from];
    const b = route.nodes[s.to];
    if (!a || !b) continue;
    if (s.edge_type === "walk") {
      if (a.floor === floor && b.floor === floor) {
        lines.push({
          x1: a.x, y1: a.y, x2: b.x, y2: b.y,
          edge_type: s.edge_type, seconds: s.time_s, meters: s.distance_meter,
        });
      }
    } else if (a.floor === floor) {
      badges.push({ x: a.x, y: a.y, edge_type: s.edge_type, to_floor: b.floor, seconds: s.time_s });
    } else if (b.floor === floor) {
      badges.push({ x: b.x, y: b.y, edge_type: s.edge_type, to_floor: a.floor, seconds: s.time_s });
    }
  }
  return { lines, badges };
}
