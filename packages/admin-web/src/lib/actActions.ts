/** 活动动作矩阵（与 content-service ACT_TARGET_ROLES 镜像）+ 券余量语气。 */

export type ActStatus = "draft" | "pending" | "active" | "ended" | "archived";
export type ActTarget = "pending" | "active" | "draft" | "ended" | "archived";

const TARGET_ROLES: Record<ActTarget, string[]> = {
  pending: ["platform_admin", "venue_admin", "venue_editor", "merchant"],
  active: ["platform_admin", "venue_admin"],
  ended: ["platform_admin", "venue_admin"],
  archived: ["platform_admin", "venue_admin"],
  draft: ["platform_admin", "venue_admin", "venue_editor"],
};

const NEXT: Record<ActStatus, { target: ActTarget; label: string; kind: "primary" | "ghost" | "danger" }[]> = {
  draft: [{ target: "pending", label: "提交审核", kind: "primary" }],
  pending: [
    { target: "active", label: "上线活动", kind: "primary" },
    { target: "draft", label: "驳回", kind: "ghost" },
  ],
  active: [{ target: "ended", label: "结束", kind: "danger" }],
  ended: [{ target: "archived", label: "归档", kind: "ghost" }],
  archived: [],
};

export function availableActActions(status: ActStatus, roles: string[]) {
  return (NEXT[status] ?? []).filter(
    (a) => TARGET_ROLES[a.target].some((r) => roles.includes(r)),
  );
}

export const ACT_STATUS_ZH: Record<ActStatus, string> = {
  draft: "草稿", pending: "待上线", active: "进行中", ended: "已结束", archived: "已归档",
};

export const ACT_TYPE_ZH: Record<string, string> = {
  mall_activity: "商场活动", brand_activity: "品牌活动", shop_promo: "商户促销",
  coupon: "券活动", full_reduction: "满减", package: "套餐", flash_sale: "限时抢",
  new_store: "新店开业",
};

export function remainingTone(remaining: number): string {
  if (remaining <= 0) return "red";
  if (remaining <= 5) return "amber";
  return "green";
}
