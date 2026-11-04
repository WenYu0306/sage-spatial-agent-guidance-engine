/** 路线缓存载荷（M5 event: route / GET /api/v1/route/{id} 同构）。 */

export interface RouteSummary {
  distance_meter: number;
  eta_seconds: number;
  floors: string[];
  transfers: Array<{ type: string; from: string | null; to: string | null }>;
}

export interface RouteNode {
  label: string;
  floor: string;
  x: number;
  y: number;
}

export interface RouteSegment {
  from_id: number;
  to_id: number;
  edge_type: string;
  distance_meter: number;
  time_s: number;
}

export interface RoutePayload {
  route_id: number;
  venue_id: number;
  start_label: string | null;
  goal_label: string | null;
  summary: RouteSummary;
  nodes: Record<string, RouteNode>;
  segments: RouteSegment[];
}

export interface RouteDataLike {
  start_label: string;
  goal_label: string;
  total_distance_meter: number;
  total_time_s: number;
  nodes: Record<number, { id: number; x: number; y: number; floor: string; label: string }>;
  segments: Array<{ from: number; to: number; edge_type: string;
                    distance_meter: number; time_s: number }>;
}

/** M5 路线载荷 → map-render routeDraw 需要的结构（纯函数）。 */
export function toRouteData(p: RoutePayload): RouteDataLike {
  const nodes: RouteDataLike["nodes"] = {};
  for (const [key, node] of Object.entries(p.nodes)) {
    nodes[Number(key)] = { id: Number(key), x: node.x, y: node.y,
                           floor: node.floor, label: node.label };
  }
  return {
    start_label: p.start_label ?? "",
    goal_label: p.goal_label ?? "",
    total_distance_meter: p.summary.distance_meter,
    total_time_s: p.summary.eta_seconds,
    nodes,
    segments: p.segments.map((s) => ({
      from: s.from_id, to: s.to_id, edge_type: s.edge_type,
      distance_meter: s.distance_meter, time_s: s.time_s,
    })),
  };
}

/** 扫码接力落地页地址（M12 契约：/m/route/{route_id}）。 */
export function qrTarget(routeId: number, origin: string): string {
  return `${origin.replace(/\/+$/, "")}/m/route/${routeId}`;
}
