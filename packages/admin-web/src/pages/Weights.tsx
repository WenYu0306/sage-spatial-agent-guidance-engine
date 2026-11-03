/** 推荐权重（只读展示，F-16 冻结）：GET /recommend/weights。 */
import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api.ts";
import { Badge, LoadError, Spinner } from "../components/ui.tsx";

const FACTOR_ZH: Record<string, string> = {
  distance: "距离", floor_diff: "楼层差", business: "营业状态",
  promotion: "当前优惠", merchant: "商户推荐权重", hot: "热度",
  tag_match: "标签匹配", convenience: "位置便利度",
};

export default function WeightsPage() {
  const query = useQuery({
    queryKey: ["weights"],
    queryFn: () => api<{ factors: Record<string, number>; scales: Record<string, number>; editable: boolean; note: string }>(
      "/recommend/weights"),
    staleTime: 60_000,
  });
  if (query.isPending) return <Spinner />;
  if (query.isError) return <LoadError error={query.error} onRetry={() => void query.refetch()} />;
  const { factors, scales, note } = query.data;
  return (
    <div className="max-w-xl">
      <div className="mb-4 flex items-center gap-2">
        <h2 className="text-lg font-semibold text-slate-800">推荐权重（八因子）</h2>
        <Badge tone="amber">V1 冻结 · 不可后台调</Badge>
      </div>
      <p className="mb-4 text-xs text-slate-400">{note}</p>
      <div className="space-y-2">
        {Object.entries(factors).map(([k, w]) => (
          <div key={k} className="flex items-center gap-3">
            <span className="w-24 text-sm text-slate-600">{FACTOR_ZH[k] ?? k}</span>
            <div className="h-3 flex-1 overflow-hidden rounded-full bg-slate-100">
              <div className="h-full rounded-full bg-slate-600"
                style={{ width: `${Math.round(w * 100) * 4}%` }} />
            </div>
            <span className="w-12 text-right text-sm font-medium text-slate-700">{w.toFixed(2)}</span>
          </div>
        ))}
      </div>
      <div className="mt-6 rounded-lg bg-slate-50 p-4 text-xs text-slate-500">
        归一化刻度：距离 {scales.distance_m}m · 楼层差 {scales.floor_diff} 层 · 主动线 {scales.trunk_m}m
        <br />调权流程：改 packages/recommender/config/recommend_weights.yaml → git 评审 → 重启服务生效
      </div>
    </div>
  );
}
