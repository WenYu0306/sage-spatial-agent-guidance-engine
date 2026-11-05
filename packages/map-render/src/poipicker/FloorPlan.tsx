/** 分层平面图：真实底图（scripts/gen_floor_maps.py 产出，floors.ts 内嵌）+ 点位标记 + 点击拾点。 */

import { useRef } from "react";
import { FLOOR_SVGS, FLOOR_VIEWBOX } from "../assets/floors.ts";
import { clientToSvg, inBounds, snap } from "../lib/svgCoords.ts";
/** 渲染标记只需四个字段；PoiPoint 结构天然满足。 */
export interface MapMarker {
  name: string;
  floor: string;
  x: number;
  y: number;
}

const CORRIDORS: Array<[number, number, number, number]> = [
  // 与 seed 路网走廊一致：北排/南排/三条纵向连接（仅资产缺失时兜底显示）
  [150, 260, 1050, 260],
  [150, 560, 1050, 560],
  [150, 260, 150, 560],
  [600, 260, 600, 560],
  [1050, 260, 1050, 560],
];

function fallbackBase(floor: string): string {
  const walls =
    '<rect x="10" y="10" width="1180" height="780" rx="12" fill="white" stroke="#94a3b8" stroke-width="3"/>';
  const lines = CORRIDORS.map(
    ([x1, y1, x2, y2]) =>
      `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="#cbd5e1" stroke-width="26" stroke-linecap="round"/>`,
  ).join("");
  return `<g>${walls}${lines}<text x="40" y="60" font-size="34" fill="#475569">${floor} 层（底图资产缺失，显示占位网格）</text></g>`;
}

interface Props {
  floor: string;
  points: MapMarker[];
  draft?: { x: number; y: number } | null;
  onPick?: (x: number, y: number) => void;
  overlay?: React.ReactNode;
}

export function FloorPlan({ floor, points, draft = null, onPick, overlay }: Props) {
  const svgRef = useRef<SVGSVGElement | null>(null);

  function handleClick(e: React.MouseEvent<SVGSVGElement>) {
    if (!onPick) return;
    const svg = svgRef.current;
    if (!svg) return;
    const { x, y } = clientToSvg(svg, e.clientX, e.clientY);
    const vb = (FLOOR_VIEWBOX[floor] ?? "0 0 1200 800").split(" ").map(Number);
    if (!inBounds(x, y, vb[2], vb[3])) return;
    onPick(snap(x), snap(y));
  }

  const shown = points.filter((p) => p.floor === floor);
  const base = FLOOR_SVGS[floor] ?? fallbackBase(floor);

  return (
    <svg
      ref={svgRef}
      viewBox={FLOOR_VIEWBOX[floor] ?? "0 0 1200 800"}
      onClick={handleClick}
      style={{ width: "100%", display: "block", background: "#f8fafc", borderRadius: 8 }}
    >
      <g dangerouslySetInnerHTML={{ __html: base }} />
      {shown.map((p) => (
        <g key={p.name}>
          <circle cx={p.x} cy={p.y} r={9} fill="#2563eb" fillOpacity={0.85} stroke="white" strokeWidth={2.5} />
          <text x={p.x + 13} y={p.y + 5} fontSize={19} fill="#1e293b">{p.name}</text>
        </g>
      ))}
      {draft && (
        <g>
          <circle cx={draft.x} cy={draft.y} r={12} fill="none" stroke="#dc2626" strokeWidth={3} />
          <circle cx={draft.x} cy={draft.y} r={4} fill="#dc2626" />
        </g>
      )}
      {overlay}
    </svg>
  );
}
