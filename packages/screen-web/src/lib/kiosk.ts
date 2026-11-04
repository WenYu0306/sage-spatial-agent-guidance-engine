/** kiosk 纯逻辑：路由状态机、轮播步进、广告卡片映射（node:test 直测）。 */

export type KioskRoute = "home" | "chat" | "route";

export const IDLE_MS = 90_000;

export type KioskAction = "home" | "ask" | "route" | "idle";

export function nextRoute(prev: KioskRoute, action: KioskAction): KioskRoute {
  if (action === "idle" || action === "home") return "home";
  if (action === "ask") return "chat";
  if (action === "route") return "route";
  return prev;
}

export interface AdCard {
  key: string;
  kind: "activity" | "coupon";
  title: string;
  detail: string;
}

interface ActivityRow {
  id: number;
  title: string;
  act_type?: string | null;
  description?: string | null;
}

interface CouponRow {
  id: number;
  title: string;
  coupon_type?: string | null;
  threshold?: number | null;
  value?: number | null;
}

export function toAdCards(activities: ActivityRow[], coupons: CouponRow[]): AdCard[] {
  const acts = (activities ?? []).map((a) => ({
    key: `a-${a.id}`,
    kind: "activity" as const,
    title: a.title,
    detail: a.description || "限时活动进行中",
  }));
  const cps = (coupons ?? []).map((c) => ({
    key: `c-${c.id}`,
    kind: "coupon" as const,
    title: c.title,
    detail: c.coupon_type === "discount"
      ? `${(c.value ?? 0) / 10} 折`
      : c.coupon_type === "gift"
        ? "赠品券"
        : `满 ${c.threshold ?? 0} 减 ${c.value ?? 0}`,
  }));
  return [...acts, ...cps];
}

export function carouselStep(total: number, index: number): number {
  if (total <= 0) return 0;
  return (index + 1) % total;
}
