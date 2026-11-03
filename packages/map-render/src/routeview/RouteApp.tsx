/** 路线渲染演示：楼层切换 + 分段画线 + 换乘标记（数据源为内置 mock，M5 接实时输出）。 */

import { useState } from "react";
import { floorPolylines } from "../lib/routeDraw.ts";
import type { RouteData } from "../lib/routeDraw.ts";
import { FloorPlan } from "../poipicker/FloorPlan.tsx";
import { MapStage } from "../poipicker/MapStage.tsx";
import { MOCK_ROUTE } from "./mockRoute.ts";

const FLOORS = ["B1", "F1", "F2"] as const;
const LINE_COLOR: Record<string, string> = {
  walk: "#2563eb",
  elevator: "#ea580c",
  escalator: "#9333ea",
};

function overlayFor(route: RouteData, floor: string) {
  const { lines, badges } = floorPolylines(route, floor);
  return (
    <g>
      {lines.map((l) => (
        <line key={`${l.x1},${l.y1}-${l.x2},${l.y2}`} x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2}
          stroke={LINE_COLOR[l.edge_type] ?? "#2563eb"} strokeWidth={8}
          strokeLinecap="round" opacity={0.85} />
      ))}
      {badges.map((b) => (
        <g key={`${b.x},${b.y},${b.to_floor}`}>
          <circle cx={b.x} cy={b.y} r={20} fill={LINE_COLOR[b.edge_type] ?? "#ea580c"} opacity={0.9} />
          <text x={b.x} y={b.y + 7} fontSize={22} textAnchor="middle" fill="white">⇅</text>
          <text x={b.x} y={b.y + 42} fontSize={19} textAnchor="middle" fill="#1e293b">
            {b.edge_type}→{b.to_floor}
          </text>
        </g>
      ))}
    </g>
  );
}

export function RouteApp() {
  const [floor, setFloor] = useState<string>("B1");
  const route = MOCK_ROUTE;
  const nodes = Object.values(route.nodes);

  return (
    <div style={{ fontFamily: "system-ui, sans-serif", padding: 16, maxWidth: 1280, margin: "0 auto" }}>
      <h1 style={{ fontSize: 22, margin: "0 0 8px" }}>
        路线渲染 · {route.start_label} → {route.goal_label}
        <span style={{ fontSize: 13, color: "#64748b", marginLeft: 12 }}>
          {route.total_distance_meter} 米 / {route.total_time_s} 秒（mock，与 M3 demo 输出同构）
        </span>
      </h1>
      <div style={{ marginBottom: 10, display: "flex", gap: 8 }}>
        {FLOORS.map((f) => (
          <button key={f} onClick={() => setFloor(f)}
            style={{ background: floor === f ? "#2563eb" : "#e2e8f0", color: floor === f ? "white" : "#0f172a",
              border: "none", borderRadius: 6, padding: "7px 16px", cursor: "pointer", fontSize: 14 }}>
            {f}
          </button>
        ))}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 16 }}>
        <MapStage>
          <FloorPlan floor={floor} overlay={overlayFor(route, floor)}
            points={nodes.map((n) => ({ name: n.label, floor: n.floor, x: n.x, y: n.y }))} />
        </MapStage>
        <fieldset style={{ border: "1px solid #e2e8f0", borderRadius: 8 }}>
          <legend>分段（共 {route.segments.length} 段）</legend>
          <ol style={{ margin: 0, paddingLeft: 20, fontSize: 13, lineHeight: 1.7 }}>
            {route.segments.map((s, i) => {
              const a = route.nodes[s.from];
              const b = route.nodes[s.to];
              const active = a.floor === floor || b.floor === floor;
              return (
                <li key={i} style={{ color: active ? "#0f172a" : "#94a3b8" }}>
                  <b style={{ color: LINE_COLOR[s.edge_type] }}>[{s.edge_type}]</b>{" "}
                  {a.label}({a.floor}) → {b.label}({b.floor})<br />
                  <small>{s.distance_meter}m / {s.time_s}s</small>
                </li>
              );
            })}
          </ol>
        </fieldset>
      </div>
    </div>
  );
}
