/** hash 路由解析（纯函数，node:test 直测）。 */

export type MobilePage =
  | { page: "route"; id: number }
  | { page: "search" }
  | { page: "chat" }
  | { page: "coupons" }
  | { page: "poi"; id: number };

/** "#/m/route/7" → 落地接力；"#/poi/12" → 详情；缺省 → 搜索页。 */
export function parseHash(hash: string): MobilePage {
  const path = hash.replace(/^#/, "").replace(/\/+$/, "");
  const parts = path.split("/").filter(Boolean);
  if (parts[0] === "m" && parts[1] === "route" && parts[2]) {
    const id = Number(parts[2]);
    if (Number.isInteger(id) && id > 0) return { page: "route", id };
  }
  if (parts[0] === "route" && parts[1]) {
    const id = Number(parts[1]);
    if (Number.isInteger(id) && id > 0) return { page: "route", id };
  }
  if (parts[0] === "poi" && parts[1]) {
    const id = Number(parts[1]);
    if (Number.isInteger(id) && id > 0) return { page: "poi", id };
  }
  if (parts[0] === "chat") return { page: "chat" };
  if (parts[0] === "coupons") return { page: "coupons" };
  return { page: "search" };
}

export function navTo(page: MobilePage): string {
  switch (page.page) {
    case "route": return `#/m/route/${page.id}`;
    case "poi": return `#/poi/${page.id}`;
    case "chat": return "#/chat";
    case "coupons": return "#/coupons";
    default: return "#/search";
  }
}
