/** 发布动作矩阵（与 content-service POI_TARGET_ROLES 严格镜像，改动须两侧同步）。 */

export type PoiStatus = "draft" | "pending" | "published" | "offline";
export type PoiTarget = "pending" | "published" | "offline" | "draft";

const TARGET_ROLES: Record<PoiTarget, string[]> = {
  pending: ["platform_admin", "venue_admin", "venue_editor", "merchant"],
  published: ["platform_admin", "venue_admin"],
  offline: ["platform_admin", "venue_admin"],
  draft: ["platform_admin", "venue_admin", "venue_editor"],
};

const NEXT: Record<PoiStatus, { target: PoiTarget; label: string; kind: "primary" | "ghost" | "danger" }[]> = {
  draft: [{ target: "pending", label: "提交审核", kind: "primary" }],
  pending: [
    { target: "published", label: "审核通过", kind: "primary" },
    { target: "draft", label: "驳回", kind: "ghost" },
  ],
  published: [{ target: "offline", label: "下架", kind: "danger" }],
  offline: [{ target: "draft", label: "回草稿", kind: "ghost" }],
};

export function availableActions(status: PoiStatus, roles: string[]) {
  return (NEXT[status] ?? []).filter(
    (a) => TARGET_ROLES[a.target].some((r) => roles.includes(r)),
  );
}

export function buildPoiQuery(f: {
  keyword?: string; category?: string; floorId?: number | null;
  status?: string; openNow?: boolean; page: number; pageSize: number;
}): string {
  const q = new URLSearchParams();
  if (f.keyword) q.set("keyword", f.keyword);
  if (f.category) q.set("category_code", f.category);
  if (f.floorId != null) q.set("floor_id", String(f.floorId));
  if (f.status) q.set("status", f.status);
  if (f.openNow) q.set("open_now", "true");
  q.set("page", String(f.page));
  q.set("page_size", String(f.pageSize));
  return q.toString();
}
