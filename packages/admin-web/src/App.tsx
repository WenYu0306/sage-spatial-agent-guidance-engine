/** 后台外壳：侧边导航 + 用户信息 + hash 路由分发。 */
import { useQueryClient } from "@tanstack/react-query";

import { decodeJwtPayload, profileStore, tokenStore } from "./lib/auth.ts";
import { navigate, useHashRoute } from "./router.tsx";
import { Badge, Button, ToastHost } from "./components/ui.tsx";
import LoginPage from "./pages/Login.tsx";
import PoisPage from "./pages/Pois.tsx";
import VenuesPage from "./pages/Venues.tsx";

const NAV = [
  { path: "/venues", label: "场地列表", roles: ["platform_admin", "venue_admin"] },
  { path: "/pois", label: "POI 管理", roles: [] },
  { path: "/activities", label: "活动管理", roles: [] },
  { path: "/coupons", label: "优惠管理", roles: [] },
  { path: "/knowledge", label: "知识内容", roles: ["platform_admin", "venue_admin", "venue_editor"] },
  { path: "/weights", label: "推荐权重", roles: [] },
  { path: "/devices", label: "设备列表", roles: [] },
  { path: "/users", label: "账号与角色", roles: ["platform_admin", "venue_admin"] },
  { path: "/dashboard", label: "数据看板", roles: [] },
];

export default function App() {
  const route = useHashRoute();
  const authed = tokenStore().get() !== null;
  // 声明式守卫：未登录一律渲染登录页（不在渲染期改 hash，规避事件时序竞态）
  if (!authed || route === "/login") {
    return (
      <ToastHost>
        <LoginPage />
      </ToastHost>
    );
  }
  return <ToastHost><Shell route={route} /></ToastHost>;
}

function Shell({ route }: { route: string }) {
  const token = tokenStore().get() ?? "";
  const payload = decodeJwtPayload(token);
  const queryClient = useQueryClient();
  const roles = payload?.roles ?? [];
  const userRole = roles[0] ?? "guest";
  return (
    <div className="flex min-h-screen bg-slate-50">
      <aside className="w-52 shrink-0 border-r border-slate-200 bg-white p-4">
        <p className="mb-1 text-sm font-semibold text-slate-800">栖云广场运营后台</p>
        <p className="mb-6 text-xs text-slate-400">M10 admin-web</p>
        <nav className="space-y-1">
          {NAV.map((item) => {
            const active = route.startsWith(item.path);
            const denied = item.roles.length > 0 && !item.roles.some((r) => roles.includes(r));
            return (
              <a
                key={item.path}
                href={`#${item.path}`}
                className={`flex items-center justify-between rounded-md px-3 py-1.5 text-sm ${
                  active ? "bg-slate-800 text-white" : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                {item.label}
                {denied && <Badge tone="amber">无权限</Badge>}
              </a>
            );
          })}
        </nav>
      </aside>
      <main className="flex-1 p-6">
        <header className="mb-6 flex items-center justify-between">
          <div className="text-sm text-slate-500">
            {profileStore().get()?.display_name ?? payload?.sub} · <Badge tone="blue">{userRole}</Badge>
            {payload?.merchant_id != null && <span className="ml-2 text-xs">门店 #{payload.merchant_id}</span>}
          </div>
          <Button
            kind="ghost"
            size="sm"
            onClick={() => {
              tokenStore().clear();
              profileStore().clear();
              void queryClient.clear();
              navigate("/login");
            }}
          >
            退出登录
          </Button>
        </header>
        <Page route={route} />
      </main>
    </div>
  );
}

function Page({ route }: { route: string }) {
  if (route.startsWith("/pois")) return <PoisPage />;
  if (route.startsWith("/activities")) return <ComingSoon title="活动管理" note="B3 交付" />;
  if (route.startsWith("/coupons")) return <ComingSoon title="优惠管理" note="B3 交付" />;
  if (route.startsWith("/knowledge")) return <ComingSoon title="知识内容" note="B3 交付" />;
  if (route.startsWith("/weights")) return <ComingSoon title="推荐权重" note="B4 交付" />;
  if (route.startsWith("/devices")) return <ComingSoon title="设备列表" note="B4 交付" />;
  if (route.startsWith("/users")) return <ComingSoon title="账号与角色" note="B4 交付" />;
  if (route.startsWith("/dashboard")) return <ComingSoon title="数据看板" note="B4 交付（M9 未接入空态）" />;
  return <VenuesPage />;
}

function ComingSoon({ title, note }: { title: string; note: string }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-white p-10 text-center">
      <p className="text-sm font-medium text-slate-600">{title}</p>
      <p className="mt-1 text-xs text-slate-400">{note}</p>
    </div>
  );
}
