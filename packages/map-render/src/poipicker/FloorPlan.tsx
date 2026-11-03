/** 占位分层平面图：外墙 + 走廊线（与 seed 路网走廊一致）+ 点位标记层 + 点击拾点。 */

import { useRef } from "react";
import { clientToSvg, inBounds, snap } from "../lib/svgCoords.ts";
import type { PoiPoint } from "../lib/types.ts";

const CORRIDORS: Array<[number, number, number, number]> = [
  // 与 seed CORRIDOR_POINTS 对应：北排/南排/三条纵向连接
  [150, 260, 1050, 260],
  [150, 560, 1050, 560],
  [150, 260, 150, 560],
  [600, 260, 600, 560],
  [1050, 260, 1050, 560],
];

interface Props {
  floor: string;
  points: PoiPoint[];
  draft: PoiPoint | null;
  onPick: (x: number, y: number) => void;
}

export function FloorPlan({ floor, points, draft, onPick }: Props) {
  const svgRef = useRef<SVGSVGElement | null>(null);

  function handleClick(e: React.MouseEvent<SVGSVGElement>) {
    const svg = svgRef.current;
    if (!svg) return;
    const { x, y } = clientToSvg(svg, e.clientX, e.clientY);
    if (!inBounds(x, y)) return;
    onPick(snap(x), snap(y));
  }

  const shown = points.filter((p) => p.floor === floor);

  return (
    <svg
      ref={svgRef}
      viewBox="0 0 1200 800"
      onClick={handleClick}
      style={{ width: "100%", display: "block", background: "#f8fafc", borderRadius: 8 }}
    >
      <rect x={10} y={10} width={1180} height={780} fill="white" stroke="#94a3b8" strokeWidth={3} rx={12} />
      {CORRIDORS.map(([x1, y1, x2, y2]) => (
        <line key={`${x1}-${y1}-${x2}-${y2}`} x1={x1} y1={y1} x2={x2} y2={y2}
          stroke="#cbd5e1" strokeWidth={26} strokeLinecap="round" />
      ))}
      <text x={40} y={60} fontSize={34} fill="#475569">{floor} 层（占位底图，M4 后续接真实 SVG）</text>
      {shown.map((p) => (
        <g key={p.name}>
          <circle cx={p.x} cy={p.y} r={9} fill="#2563eb" stroke="white" strokeWidth={2.5} />
          <text x={p.x + 13} y={p.y + 5} fontSize={19} fill="#1e293b">{p.name}</text>
        </g>
      ))}
      {draft && (
        <g>
          <circle cx={draft.x} cy={draft.y} r={12} fill="none" stroke="#dc2626" strokeWidth={3} />
          <circle cx={draft.x} cy={draft.y} r={4} fill="#dc2626" />
        </g>
      )}
    </svg>
  );
}
