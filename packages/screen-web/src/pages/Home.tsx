/** 大屏首页：欢迎语 + 快捷入口 + 闲置轮播（活动/优惠券，ad_impression/ad_click 打点）。 */

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Empty, KioskShell, LoadError, Spinner } from "../components/ui.tsx";
import { ApiError, apiFetch } from "@sage/map-render/src/lib/http/api.ts";
import type { DeviceIdentity } from "../lib/device.ts";
import { buildEvent, track } from "@sage/map-render/src/lib/http/events.ts";
import {
  carouselStep,
  toAdCards,
  type AdCard,
  type KioskAction,
} from "../lib/kiosk.ts";

const ROTATE_MS = 6_000;

export function Home({
  session,
  onAsk,
  onAuthLost,
}: {
  session: DeviceIdentity;
  onAsk: (action: KioskAction, seed?: string) => void;
  onAuthLost: () => void;
}) {
  const adsQ = useQuery({
    queryKey: ["ads", session.venueId],
    queryFn: async (): Promise<AdCard[]> => {
      try {
        const [acts, cps] = await Promise.all([
          apiFetch<{ items: Parameters<typeof toAdCards>[0] }>(
            "/api/v1/activities?status=active&page_size=12", { token: session.token }),
          apiFetch<{ items: Parameters<typeof toAdCards>[1] }>(
            "/api/v1/coupons?status=active&page_size=12", { token: session.token }),
        ]);
        return toAdCards(acts.items, cps.items);
      } catch (cause) {
        if (cause instanceof ApiError && cause.status === 401) onAuthLost();
        throw cause;
      }
    },
  });

  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1_000);
    return () => clearInterval(t);
  }, []);

  const ads = adsQ.data ?? [];
  const [adIndex, setAdIndex] = useState(0);
  const seenRef = useRef<Set<string>>(new Set());
  useEffect(() => {
    if (ads.length <= 1) return;
    const t = setInterval(() => setAdIndex((i) => carouselStep(ads.length, i)), ROTATE_MS);
    return () => clearInterval(t);
  }, [ads.length]);
  useEffect(() => {
    const card = ads[adIndex];
    if (!card || seenRef.current.has(card.key)) return;
    seenRef.current.add(card.key);
    track(buildEvent({
      tenantId: session.tenantId, venueId: session.venueId,
      eventType: "ad_impression", deviceId: session.deviceId,
      payload: { ad_key: card.key, kind: card.kind, title: card.title },
    }));
  }, [ads, adIndex, session]);

  if (adsQ.isLoading) {
    return (
      <KioskShell>
        <div className="flex flex-1 items-center justify-center">
          <Spinner label="首页加载中" />
        </div>
      </KioskShell>
    );
  }
  if (adsQ.isError) {
    const cause = adsQ.error as ApiError;
    if (cause?.status === 401) return null; // onAuthLost 已触发重登
    return (
      <KioskShell>
        <div className="flex flex-1 items-center justify-center">
          <LoadError detail={cause?.message ?? "内容加载失败"} onRetry={() => adsQ.refetch()} />
        </div>
      </KioskShell>
    );
  }
  const card = ads[adIndex];
  const quick: Array<{ label: string; seed: string }> = [
    { label: "问一问", seed: "" },
    { label: "找美食", seed: "有没有适合聚餐的餐厅？" },
    { label: "找店铺", seed: "推荐一家服饰店" },
    { label: "卫生间在哪", seed: "最近的卫生间在哪里？" },
  ];
  return (
    <KioskShell>
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-5xl font-bold tracking-wide">
            {session.venueName}
          </h1>
          <p className="mt-2 text-2xl text-slate-400">
            欢迎光临 · 营业时间 {session.businessHours ?? "10:00-22:00"}
          </p>
        </div>
        <div className="text-right">
          <div className="font-mono text-6xl font-semibold text-sky-300">
            {now.toLocaleTimeString("zh-CN", { hour12: false })}
          </div>
          <div className="mt-1 text-xl text-slate-400">
            {now.toLocaleDateString("zh-CN", { month: "long", day: "numeric", weekday: "long" })}
          </div>
        </div>
      </header>

      <main className="grid flex-1 grid-cols-2 content-center gap-8 py-10">
        {quick.map((q) => (
          <button key={q.label}
            onClick={() => onAsk("ask", q.seed)}
            className="rounded-3xl bg-slate-800/70 py-14 text-4xl font-semibold
                       shadow-lg transition hover:bg-sky-700/80 active:scale-[0.99]">
            {q.label}
          </button>
        ))}
      </main>

      <footer className="rounded-2xl bg-slate-900/80 px-8 py-5">
        {ads.length === 0 ? (
          adsQ.isError ? (
            <Empty text="活动信息暂时拿不到（服务异常，已静默重试）" />
          ) : (
            <Empty text="暂无进行中的活动" />
          )
        ) : (
          <div>
            <button
              onClick={() => {
                if (!card) return;
                track(buildEvent({
                  tenantId: session.tenantId, venueId: session.venueId,
                  eventType: "ad_click", deviceId: session.deviceId,
                  payload: { ad_key: card.key, kind: card.kind, title: card.title },
                }));
              }}
              className="block w-full text-left"
            >
              <span className="mr-3 rounded-md bg-sky-600 px-3 py-1 text-lg">
                {card.kind === "coupon" ? "优惠" : "活动"}
              </span>
              <span className="text-3xl font-semibold">{card.title}</span>
              <span className="ml-4 text-2xl text-slate-400">{card.detail}</span>
            </button>
            <div className="mt-3 flex gap-2">
              {ads.map((a, i) => (
                <span key={a.key}
                  className={`h-2 w-8 rounded-full ${i === adIndex ? "bg-sky-400" : "bg-slate-700"}`} />
              ))}
            </div>
          </div>
        )}
      </footer>
    </KioskShell>
  );
}
