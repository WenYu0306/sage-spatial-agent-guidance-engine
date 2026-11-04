/** 扫码接力落地 + 路线详情（F-11/PRD 75-76/845）：按 route_id 取缓存路线。 */

import { useQuery } from "@tanstack/react-query";
import { floorPolylines } from "@sage/map-render/src/lib/routeDraw.ts";
import type { RouteData } from "@sage/map-render/src/lib/routeDraw.ts";
import { FloorPlan } from "@sage/map-render/src/poipicker/FloorPlan.tsx";
import { apiFetch } from "@sage/map-render/src/lib/http/api.ts";
import { useState } from "react";
import { Empty, LoadError, Skeleton, TopBar } from "../components/ui.tsx";
import type { RoutePayload } from "../lib/routeShape.ts";

const LINE_COLOR: Record<string, string> = {
  walk: "#2563eb", elevator: "#ea580c", escalator: "#9333ea",
};

function overlayFor(route: RouteData, floor: string) {
  const { lines, badges } = floorPolylines(route, floor);
  return (
    <g>
      {lines.map((l) => (
        <line key={`${l.x1},${l.y1}-${l.x2},${l.y2}`} x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2}
          stroke={LINE_COLOR[l.edge_type] ?? "#2563eb"} strokeWidth={9}
          strokeLinecap="round" opacity={0.88} />
      ))}
      {badges.map((b) => (
        <g key={`${b.x},${b.y},${b.to_floor}`}>
          <circle cx={b.x} cy={b.y} r={20} fill={LINE_COLOR[b.edge_type] ?? "#ea580c"} opacity={0.9} />
          <text x={b.x} y={b.y + 7} fontSize={22} textAnchor="middle" fill="white">⇅</text>
        </g>
      ))}
    </g>
  );
}

function toRouteData(p: RoutePayload): RouteData {
  const nodes: RouteData["nodes"] = {};
  for (const [key, n] of Object.entries(p.nodes)) {
    nodes[Number(key)] = { id: Number(key), x: n.x, y: n.y, floor: n.floor, label: n.label };
  }
  return {
    start_label: p.start_label ?? "", goal_label: p.goal_label ?? "",
    total_distance_meter: p.summary.distance_meter, total_time_s: p.summary.eta_seconds,
    nodes,
    segments: p.segments.map((s) => ({
      from: s.from_id, to: s.to_id, edge_type: s.edge_type,
      distance_meter: s.distance_meter, time_s: s.time_s,
    })),
  };
}

export function RoutePage({ routeId }: { routeId: number }) {
  const [floor, setFloor] = useState<string>("");
  const q = useQuery({
    queryKey: ["route", routeId],
    queryFn: () => apiFetch<RoutePayload>(`/api/v1/route/${routeId}`),
    retry: (count, error) => (error as { status?: number })?.status === 0 && count < 2,
  });

  if (q.isLoading) {
    return (
      <div>
        <TopBar title="接力路线" />
        <Skeleton rows={4} />
      </div>
    );
  }
  if (q.isError) {
    const status = (q.error as { status?: number })?.status;
    if (status === 404) {
      return (
        <div>
          <TopBar title="接力路线" />
          <Empty text="路线已过期（30 分钟有效），请在大屏重新查询" />
          <p className="px-6 text-center text-xs text-slate-400">
            也可以点底部「找店」继续探索商场
          </p>
        </div>
      );
    }
    return (
      <div>
        <TopBar title="接力路线" />
        <LoadError detail="网络开小差了" onRetry={() => q.refetch()} />
      </div>
    );
  }
  const payload = q.data;
  if (!payload) return null;
  const route = toRouteData(payload);
  const floors = payload.summary.floors.length ? payload.summary.floors : ["F1"];
  const active = floors.includes(floor) ? floor : floors[0];
  const { lines } = floorPolylines(route, active);
  return (
    <div>
      <TopBar title={`${route.start_label} → ${route.goal_label}`} />
      <div className="px-3 pt-3">
        <div className="rounded-xl bg-white p-2 shadow-sm">
          <FloorPlan floor={active} points={[]} overlay={overlayFor(route, active)} />
        </div>
        <div className="mt-2 flex gap-2">
          {floors.map((f) => (
            <button key={f} onClick={() => setFloor(f)}
              className={`rounded-full px-4 py-1 text-xs ${active === f
                ? "bg-sky-600 text-white" : "bg-white text-slate-600 shadow-sm"}`}>
              {f} 层
            </button>
          ))}
        </div>
        <div className="mt-3 space-y-2">
          <div className="text-sm font-semibold text-slate-700">
            共 {payload.summary.distance_meter} 米 · 约 {Math.round(payload.summary.eta_seconds / 60 * 10) / 10} 分钟
          </div>
          {lines.length === 0 && floors[0] !== active && (
            <Empty text={`本层无路线段，请切到 ${floors.join("/")} 层查看`} />
          )}
          <ol className="space-y-2">
            {route.segments.map((s, i) => {
              const a = route.nodes[s.from];
              const b = route.nodes[s.to];
              return (
                <li key={i} className="rounded-xl bg-white p-3 text-sm shadow-sm">
                  <span className="font-semibold"
                    style={{ color: LINE_COLOR[s.edge_type] ?? "#2563eb" }}>
                    [{s.edge_type === "walk" ? "步行" : s.edge_type === "elevator" ? "直梯" : "扶梯"}]
                  </span>{" "}
                  {a?.label} → {b?.label}
                  <div className="text-xs text-slate-500">
                    {s.distance_meter} 米 · {Math.round(s.time_s)} 秒
                  </div>
                </li>
              );
            })}
          </ol>
        </div>
      </div>
    </div>
  );
}
