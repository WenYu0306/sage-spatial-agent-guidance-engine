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
