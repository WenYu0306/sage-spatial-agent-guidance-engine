/** POI 详情：营业时间（7 天 JSONB 展开）/标签/介绍/优惠。 */

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@sage/map-render/src/lib/http/api.ts";
import { Empty, LoadError, Skeleton, TopBar } from "../components/ui.tsx";
import type { RoutePayload } from "../lib/routeShape.ts";

interface PoiDetail {
  id: number;
  name: string;
  intro: string | null;
  category_code: string;
  floor_id: number;
  business_hours: Record<string, string[]> | null;
  tags: string[] | null;
  contact: string | null;
  status: string;
}

const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;
const DAY_LABEL: Record<string, string> = {
  mon: "周一", tue: "周二", wed: "周三", thu: "周四", fri: "周五", sat: "周六", sun: "周日",
};

export function PoiDetailPage({ poiId, back }: { poiId: number; back: () => void }) {
  const q = useQuery({
    queryKey: ["poi", poiId],
    queryFn: () => apiFetch<PoiDetail>(`/api/v1/pois/${poiId}?venue_id=1`),
  });
  if (q.isLoading) {
    return (
      <div>
        <TopBar title="店铺详情" back={back} />
        <Skeleton rows={3} />
      </div>
    );
  }
  if (q.isError) {
    const status = (q.error as { status?: number })?.status;
    return (
      <div>
        <TopBar title="店铺详情" back={back} />
        <LoadError detail={status === 403 ? "店铺不存在或未发布" : "加载失败"}
                   onRetry={() => q.refetch()} />
      </div>
    );
  }
  const p = q.data;
  if (!p) return null;
  const hours = DAYS.filter((d) => (p.business_hours?.[d] ?? []).length > 0)
    .map((d) => `${DAY_LABEL[d]} ${p.business_hours?.[d]?.join("、")}`);
  return (
    <div>
      <TopBar title={p.name} back={back} />
      <div className="space-y-3 p-3">
        {p.tags && p.tags.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {p.tags.map((t) => (
              <span key={t} className="rounded-full bg-sky-50 px-3 py-1 text-xs text-sky-700">
                {t}
              </span>
            ))}
          </div>
        )}
        {p.intro && (
          <div className="rounded-xl bg-white p-3 text-sm leading-6 shadow-sm">{p.intro}</div>
        )}
        <div className="rounded-xl bg-white p-3 shadow-sm">
          <div className="mb-1 text-sm font-semibold">营业时间</div>
          {hours.length === 0 ? (
            <div className="text-xs text-slate-500">以现场公告为准</div>
          ) : (
            hours.map((h) => <div key={h} className="text-xs text-slate-600">{h}</div>)
          )}
        </div>
        {p.contact && (
          <div className="rounded-xl bg-white p-3 text-sm shadow-sm">☎ {p.contact}</div>
        )}
      </div>
    </div>
  );
}

export type { RoutePayload };
