/** 路线文案语义化（U1-a）：根除「走廊点(x,y)」机器话，大屏/手机/独立路线页三端共用。 */

export const CORRIDOR_LABEL = "沿走廊";
const START_FALLBACK = "您附近";

export function fmtDistance(m: number): string {
  return `${Math.round(m)} 米`;
}

export function fmtDuration(s: number): string {
  if (s < 90) return `${Math.round(s)} 秒`;
  return `约 ${Math.round(s / 60)} 分钟`;
}

/** 后端对无 POI 名的走廊节点给「走廊点(x,y)」兜底——用户面一律归一为「沿走廊」。 */
export function friendlyLabel(label: string | null | undefined): string {
  if (!label || label === CORRIDOR_LABEL || label.startsWith("走廊点")) return CORRIDOR_LABEL;
  return label;
}

export interface CopyNode {
  label: string;
  floor: string;
}
export interface CopySegment {
  from_id?: number;  // agent/route-cache 载荷形状（手机端）
  to_id?: number;
  from?: number;     // route-engine 直出形状（大屏 kiosk）
  to?: number;
  edge_type: string;
  distance_meter: number;
  time_s: number;
}

const EDGE_VERB: Record<string, string> = {
  walk: "步行",
  elevator: "乘直梯",
  escalator: "乘扶梯",
};

/** 单段人话：垂直交通报楼层变化，步行按终点是否有店名分两种说法。 */
export function describeSegment(seg: CopySegment, nodes: Record<string, CopyNode>): string {
  const a = nodes[String(seg.from_id ?? seg.from)];
  const b = nodes[String(seg.to_id ?? seg.to)];
  const dist = fmtDistance(seg.distance_meter);
  if (seg.edge_type === "elevator" || seg.edge_type === "escalator") {
    const verb = EDGE_VERB[seg.edge_type] ?? seg.edge_type;
    return `${verb} ${a?.floor ?? "?"} → ${b?.floor ?? "?"} · ${dist}`;
  }
  const bName = friendlyLabel(b?.label);
  if (bName !== CORRIDOR_LABEL) return `步行至 ${bName} · ${dist}`;
  return `沿走廊步行 ${dist}`;
}

export function routeTitle(
  startLabel: string | null | undefined,
  goalLabel: string | null | undefined,
  distanceMeter: number,
  timeS: number,
): string {
  const start = friendlyLabel(startLabel);
  const goal = friendlyLabel(goalLabel) === CORRIDOR_LABEL ? "目的地附近" : friendlyLabel(goalLabel);
  return `${start === CORRIDOR_LABEL ? START_FALLBACK : start} → ${goal} · ${fmtDistance(distanceMeter)} · ${fmtDuration(timeS)}`;
}
