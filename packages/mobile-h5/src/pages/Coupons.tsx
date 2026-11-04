/** 优惠列表 + 领券（幂等键 coupon_id+anonymous_id；重复领取服务端返回 duplicate）。 */

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@sage/map-render/src/lib/http/api.ts";
import { useState } from "react";
import { Empty, LoadError, Skeleton, TopBar } from "../components/ui.tsx";
import { anonymousId } from "../lib/guest.ts";

interface CouponRow {
  id: number;
  title: string;
  type: string;
  threshold: number | null;
  value: number | null;
  remaining: number;
  poi_name: string | null;
}

interface ClaimResult {
  claimed: boolean;
  duplicate: boolean;
}

export function CouponsPage() {
  const [claimState, setClaimState] = useState<Record<number, string>>({});
  const q = useQuery({
    queryKey: ["coupons"],
    queryFn: () => apiFetch<{ items: CouponRow[] }>("/api/v1/coupons?venue_id=1"),
  });

  async function claim(couponId: number) {
    setClaimState((s) => ({ ...s, [couponId]: "…" }));
    try {
      const r = await apiFetch<ClaimResult>(
        `/api/v1/coupons/${couponId}/claim`,
        { method: "POST", body: JSON.stringify({ anonymous_id: anonymousId() }) },
      );
      setClaimState((s) => ({
        ...s,
        [couponId]: r.duplicate ? "已领过" : r.claimed ? "领取成功" : "暂时领完",
      }));
    } catch {
      setClaimState((s) => ({ ...s, [couponId]: "领取失败" }));
    }
  }

  return (
    <div>
      <TopBar title="优惠" />
      {q.isLoading && <Skeleton rows={3} />}
      {q.isError && <LoadError detail="优惠加载失败" onRetry={() => q.refetch()} />}
      {!q.isLoading && !q.isError && (q.data?.items ?? []).length === 0 && (
        <Empty text="暂无可领优惠" />
      )}
      <ul className="space-y-2 p-3">
        {(q.data?.items ?? []).map((c) => (
          <li key={c.id} className="flex items-center gap-3 rounded-xl bg-white p-3 shadow-sm">
            <div className="flex-1">
              <div className="text-sm font-semibold">{c.title}</div>
              <div className="text-xs text-slate-500">
                {c.poi_name ? `${c.poi_name} · ` : ""}
                {c.type === "percent" ? `${c.value ?? 0} 折` : `满 ${c.threshold ?? 0} 减 ${c.value ?? 0}`}
                {` · 剩 ${c.remaining} 张`}
              </div>
            </div>
            <button
              onClick={() => void claim(c.id)}
              disabled={c.remaining <= 0 || claimState[c.id] === "已领过"}
              className="rounded-full bg-emerald-600 px-4 py-1.5 text-xs text-white
                         disabled:bg-slate-300">
              {c.remaining <= 0 ? "已领完" : (claimState[c.id] ?? "领取")}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
