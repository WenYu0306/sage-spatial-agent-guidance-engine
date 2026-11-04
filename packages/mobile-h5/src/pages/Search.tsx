/** 搜索页：关键词找店（guest 直读 published，PRD 7.3）。 */

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@sage/map-render/src/lib/http/api.ts";
import { useState } from "react";
import { Empty, LoadError, Skeleton } from "../components/ui.tsx";

interface PoiRow {
  poi_id: number;
  name: string;
  floor: string | null;
  category_code?: string;
  open_now?: boolean;
}

export function SearchPage({ onOpenPoi }: { onOpenPoi: (id: number) => void }) {
  const [keyword, setKeyword] = useState("");
  const [submitted, setSubmitted] = useState("");
  const q = useQuery({
    queryKey: ["pois", submitted],
    queryFn: () => apiFetch<{ items: PoiRow[] }>(
      `/api/v1/pois?venue_id=1&status=published${submitted ? `&keyword=${encodeURIComponent(submitted)}` : ""}`),
    enabled: true,
  });
  const items = q.data?.items ?? [];
  return (
    <div>
      <form className="flex gap-2 p-3"
        onSubmit={(e) => { e.preventDefault(); setSubmitted(keyword.trim()); }}>
        <input value={keyword} onChange={(e) => setKeyword(e.target.value)}
          placeholder="搜索店铺，如：咖啡 / 火锅 / 书店"
          className="flex-1 rounded-full bg-white px-4 py-2 text-sm shadow-sm outline-none
                     focus:ring-2 focus:ring-sky-400" />
        <button type="submit" className="rounded-full bg-sky-600 px-5 py-2 text-sm text-white">
          搜索
        </button>
      </form>
      {q.isLoading && <Skeleton rows={4} />}
      {q.isError && (
        <LoadError detail="搜索失败，网络开小差了" onRetry={() => q.refetch()} />
      )}
      {!q.isLoading && !q.isError && items.length === 0 && (
        <Empty text={submitted ? "没找到相关店铺，换个关键词试试" : "输入关键词开始探索"} />
      )}
      <ul className="space-y-2 px-3">
        {items.map((p) => (
          <li key={p.poi_id}>
            <button onClick={() => onOpenPoi(p.poi_id)}
              className="flex w-full items-center justify-between rounded-xl bg-white p-3 text-left shadow-sm">
              <div>
                <div className="text-sm font-semibold">{p.name}</div>
                <div className="text-xs text-slate-500">
                  {p.floor ?? ""} {p.floor ? "层" : ""}
                </div>
              </div>
              <span className="text-slate-300">›</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
