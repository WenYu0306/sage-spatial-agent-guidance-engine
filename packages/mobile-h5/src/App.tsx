/** 手机 H5 App：hash 路由（#/m/route/:id 接力落地）+ 底部三 Tab。 */

import { useEffect, useState } from "react";
import { ChatPage } from "./pages/Chat.tsx";
import { CouponsPage } from "./pages/Coupons.tsx";
import { PoiDetailPage } from "./pages/PoiDetail.tsx";
import { RoutePage } from "./pages/Route.tsx";
import { SearchPage } from "./pages/Search.tsx";
import { navTo, parseHash, type MobilePage } from "./lib/router.ts";
import { IconChat, IconSearch, IconTicket } from "@sage/map-render/src/lib/icons.tsx";

const TABS: Array<{ page: MobilePage; label: string; Icon: (p: { className?: string }) => React.JSX.Element }> = [
  { page: { page: "search" }, label: "找店", Icon: IconSearch },
  { page: { page: "chat" }, label: "问一问", Icon: IconChat },
  { page: { page: "coupons" }, label: "优惠", Icon: IconTicket },
];

export function App() {
  const [route, setRoute] = useState<MobilePage>(() => parseHash(location.hash));

  useEffect(() => {
    const onHash = () => setRoute(parseHash(location.hash));
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const nav = (page: MobilePage) => {
    const target = navTo(page);
    if (target !== location.hash) location.hash = target;
  };
  return (
    <div className="mx-auto flex h-full max-w-md flex-col">
      <main className="flex-1 overflow-y-auto pb-16">
        {route.page === "route" && <RoutePage routeId={route.id} />}
        {route.page === "search" && (
          <SearchPage onOpenPoi={(id) => nav({ page: "poi", id })} />
        )}
        {route.page === "chat" && <ChatPage />}
        {route.page === "coupons" && <CouponsPage />}
        {route.page === "poi" && <PoiDetailPage poiId={route.id} back={() => nav({ page: "search" })} />}
      </main>
      <nav className="fixed inset-x-0 bottom-0 z-40 mx-auto flex max-w-md border-t border-slate-200 bg-white/95 backdrop-blur">
        {TABS.map((t) => (
          <button key={t.label} onClick={() => nav(t.page)}
            className={`flex flex-1 flex-col items-center py-2 text-xs
                        ${route.page === t.page.page ? "text-accent-deep" : "text-muted"}`}>
            <t.Icon className="size-5" />
            {t.label}
          </button>
        ))}
      </nav>
    </div>
  );
}

