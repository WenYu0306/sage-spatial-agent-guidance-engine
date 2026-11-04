/** 大屏路线页：分层地图画线 + 分段列表 + 「发到手机」二维码接力（F-11/PRD 75-76/845）。 */

import { useEffect, useMemo, useRef, useState } from "react";
import QRCode from "qrcode";
import { floorPolylines } from "@sage/map-render/src/lib/routeDraw.ts";
import type { RouteData } from "@sage/map-render/src/lib/routeDraw.ts";
import { FloorPlan } from "@sage/map-render/src/poipicker/FloorPlan.tsx";
import { MapStage } from "@sage/map-render/src/poipicker/MapStage.tsx";
import { KioskShell } from "../components/ui.tsx";
import type { DeviceIdentity } from "../lib/device.ts";
import { buildEvent, track } from "@sage/map-render/src/lib/http/events.ts";
import { qrTarget, toRouteData } from "../lib/route.ts";
import type { RoutePayload } from "../lib/route.ts";

const LINE_COLOR: Record<string, string> = {
  walk: "#38bdf8",
  elevator: "#fb923c",
  escalator: "#c084fc",
};

function overlayFor(route: RouteData, floor: string) {
  const { lines, badges } = floorPolylines(route, floor);
  return (
    <g>
      {lines.map((l) => (
        <line key={`${l.x1},${l.y1}-${l.x2},${l.y2}`} x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2}
          stroke={LINE_COLOR[l.edge_type] ?? "#38bdf8"} strokeWidth={9}
          strokeLinecap="round" opacity={0.9} />
      ))}
      {badges.map((b) => (
        <g key={`${b.x},${b.y},${b.to_floor}`}>
          <circle cx={b.x} cy={b.y} r={20}
            fill={LINE_COLOR[b.edge_type] ?? "#fb923c"} opacity={0.92} />
          <text x={b.x} y={b.y + 7} fontSize={22} textAnchor="middle" fill="#0b1220">⇅</text>
          <text x={b.x} y={b.y + 44} fontSize={19} textAnchor="middle" fill="#e2e8f0">
            {b.edge_type === "elevator" ? "直梯" : "扶梯"}→{b.to_floor}
          </text>
        </g>
      ))}
    </g>
  );
}

const EDGE_LABEL: Record<string, string> = {
  walk: "步行", elevator: "直梯", escalator: "扶梯", stairs: "楼梯",
};

export function RoutePage({
  session,
  payload,
  onBack,
}: {
  session: DeviceIdentity;
  payload: RoutePayload;
  onBack: () => void;
}) {
  const route = useMemo(() => toRouteData(payload), [payload]);
  const floors = payload.summary.floors.length > 0
    ? payload.summary.floors : ["F1"];
  const [floor, setFloor] = useState(floors[0]);
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null);
  const handoverFiredRef = useRef(false);

  useEffect(() => {
    if (!qrDataUrl || handoverFiredRef.current) return;
    handoverFiredRef.current = true;
    track(buildEvent({
      tenantId: session.tenantId, venueId: session.venueId,
      eventType: "route_handover", deviceId: session.deviceId,
      payload: { route_id: payload.route_id, session_hint: "screen-qrcode" },
    }));
  }, [qrDataUrl, session, payload.route_id]);

  async function showQr() {
    const url = await QRCode.toDataURL(qrTarget(payload.route_id, window.location.origin),
      { width: 420, margin: 2, color: { dark: "#0b1220", light: "#ffffff" } });
    setQrDataUrl(url);
  }

  return (
    <KioskShell>
      <header className="flex items-center justify-between">
        <button onClick={onBack}
          className="rounded-lg bg-slate-800 px-6 py-2 text-xl hover:bg-slate-700">
          ← 返回首页
        </button>
        <div className="text-2xl font-semibold">
          {route.start_label} → {route.goal_label}
          <span className="ml-4 text-xl text-slate-400">
            {route.total_distance_meter} 米 · 约{Math.round(route.total_time_s)} 秒
          </span>
        </div>
        <button onClick={showQr}
          className="rounded-xl bg-emerald-600 px-8 py-3 text-2xl font-semibold hover:bg-emerald-500">
          发到手机
        </button>
      </header>

      <div className="mt-4 flex gap-3">
        {floors.map((f) => (
          <button key={f} onClick={() => setFloor(f)}
            className={`rounded-lg px-6 py-2 text-xl ${floor === f
              ? "bg-sky-600 text-white" : "bg-slate-800 text-slate-300 hover:bg-slate-700"}`}>
            {f}
          </button>
        ))}
      </div>

      <div className="mt-4 grid flex-1 grid-cols-[3fr_2fr] gap-6 overflow-hidden">
        <div className="overflow-hidden rounded-2xl bg-slate-800/40">
          <MapStage>
            <FloorPlan floor={floor} points={[]} overlay={overlayFor(route, floor)} />
          </MapStage>
        </div>
        <div className="overflow-y-auto rounded-2xl bg-slate-900/70 p-5">
          <div className="mb-3 text-xl font-semibold text-slate-300">
            分段（共 {route.segments.length} 段）
          </div>
          <ol className="space-y-3">
            {route.segments.map((s, i) => {
              const a = route.nodes[s.from];
              const b = route.nodes[s.to];
              const active = a?.floor === floor || b?.floor === floor;
              return (
                <li key={i}
                  className={`rounded-xl px-4 py-3 text-xl ${active
                    ? "bg-slate-800 text-slate-100" : "bg-slate-900 text-slate-500"}`}>
                  <span className="font-semibold"
                    style={{ color: LINE_COLOR[s.edge_type] ?? "#38bdf8" }}>
                    [{EDGE_LABEL[s.edge_type] ?? s.edge_type}]
                  </span>{" "}
                  {a?.label}（{a?.floor}）→ {b?.label}（{b?.floor}）
                  <div className="text-lg text-slate-400">
                    {s.distance_meter} 米 · {Math.round(s.time_s)} 秒
                  </div>
                </li>
              );
            })}
          </ol>
        </div>
      </div>

      {qrDataUrl && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70"
             onClick={() => setQrDataUrl(null)}>
          <div className="rounded-3xl bg-slate-900 p-10 text-center"
               onClick={(e) => e.stopPropagation()}>
            <div className="text-3xl font-semibold">扫码接力到手机</div>
            <img src={qrDataUrl} alt="路线二维码"
                 className="mx-auto my-6 size-80 rounded-2xl bg-white p-2" />
            <div className="text-xl text-slate-400">
              用手机扫码，在手机上继续查看这条路线（30 分钟内有效）
            </div>
            <button onClick={() => setQrDataUrl(null)}
              className="mt-6 rounded-xl bg-slate-700 px-10 py-3 text-2xl hover:bg-slate-600">
              关闭
            </button>
          </div>
        </div>
      )}
    </KioskShell>
  );
}
