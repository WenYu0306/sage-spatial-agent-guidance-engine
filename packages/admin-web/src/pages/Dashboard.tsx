/** 数据看板（M9）：四指标卡 + 近 7 天 AI 问答条形图（纯 CSS，无图表库）。 */
import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api.ts";
import { Empty, LoadError, Spinner } from "../components/ui.tsx";

type Overview = { metrics: Record<string, number> };

const CARD_ZH: Record<string, string> = {
  ai_query_count: "AI 咨询次数",
  route_plan_count: "导航次数",
  coupon_claim_count: "领券次数",
  device_usage_count: "设备活跃",
};

function lastNDays(n: number): { from: string; to: string } {
  const to = new Date();
  const from = new Date(Date.now() - (n - 1) * 86400_000);
  return { from: from.toISOString().slice(0, 10), to: to.toISOString().slice(0, 10) };
}

export default function DashboardPage() {
  const range = lastNDays(7);
  const overview = useQuery({
    queryKey: ["metrics", "overview", range.from, range.to],
    queryFn: () =>
      api<Overview>(`/api/v1/metrics/overview?date_from=${range.from}&date_to=${range.to}`),
    retry: 1,
  });
  const series = useQuery({
    queryKey: ["metrics", "ai_query_count", "day"],
    queryFn: () =>
      api<{ points: { date: string; value: number }[] }>(
        "/api/v1/metrics/ai_query_count?granularity=day"),
    retry: 1,
  });
  if (overview.isPending || series.isPending) return <Spinner />;
  if (overview.isError) return <LoadError error={overview.error} onRetry={() => void overview.refetch()} />;
  if (series.isError) return <LoadError error={series.error} onRetry={() => void series.refetch()} />;

  const metrics = overview.data.metrics;
  const points = series.data.points;
  if (points.length === 0 && metrics.ai_query_count === 0) {
    return <Empty text="近 7 天暂无数据（大屏/手机端接入埋点后在此呈现）" />;
  }
  const maxVal = Math.max(...points.map((p) => p.value), 1);

  return (
    <div>
      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
        {Object.entries(CARD_ZH).map(([code, label]) => (
          <div key={code} className="rounded-xl bg-white p-5 shadow-sm">
            <p className="text-xs text-slate-400">{label}</p>
            <p className="mt-1 text-2xl font-semibold text-slate-800">
              {metrics[code] ?? 0}
            </p>
          </div>
        ))}
      </div>
      <h3 className="mb-3 text-sm font-medium text-slate-600">近 7 天 AI 问答量</h3>
      <div className="flex h-40 items-end gap-2 rounded-xl bg-white p-4 shadow-sm">
        {points.map((p) => (
          <div key={p.date} className="flex flex-1 flex-col items-center gap-1">
            <span className="text-xs text-slate-500">{p.value}</span>
            <div
              className="w-full rounded-t bg-slate-700"
              style={{ height: `${Math.max(4, (p.value / maxVal) * 110)}px` }}
            />
            <span className="text-[10px] text-slate-400">{p.date.slice(5)}</span>
          </div>
        ))}
        {points.length === 0 && <p className="text-xs text-slate-400">暂无时序数据</p>}
      </div>
    </div>
  );
}
