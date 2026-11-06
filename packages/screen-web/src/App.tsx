/** 大屏 App：设备会话引导 + kiosk 路由状态机 + 闲置回首页。 */

import { useCallback, useEffect, useRef, useState } from "react";
import { KioskShell, LoadError, Spinner } from "./components/ui.tsx";
import { Chat } from "./pages/Chat.tsx";
import { Home } from "./pages/Home.tsx";
import { RoutePage } from "./pages/RoutePage.tsx";
import {
  deviceLogin,
  invalidateToken,
  readScreenConfig,
  startHeartbeat,
  type DeviceIdentity,
} from "./lib/device.ts";
import { IDLE_MS, nextRoute, type KioskAction, type KioskRoute } from "./lib/kiosk.ts";
import type { RoutePayload } from "./lib/route.ts";

export function App() {
  const config = readScreenConfig();
  const [session, setSession] = useState<DeviceIdentity | null | "error" | "missing">(
    config ? null : "missing",
  );
  const [error, setError] = useState("");
  const [route, setRoute] = useState<KioskRoute>("home");
  const [chatSeed, setChatSeed] = useState("");
  const [routePayload, setRoutePayload] = useState<RoutePayload | null>(null);
  const [a11y, setA11y] = useState(() => {
    try {
      return localStorage.getItem("sage_screen_a11y") === "1";
    } catch {
      return false;
    }
  });
  const lastActive = useRef(Date.now());

  const boot = useCallback(() => {
    if (!config) return;
    setError("");
    setSession(null);
    deviceLogin(config)
      .then(setSession)
      .catch((cause: unknown) => {
        setError(cause instanceof Error ? cause.message : "设备登录失败");
        setSession("error");
      });
  }, [config?.username, config?.password, config?.venueId]);

  const onAuthLost = useCallback(() => {
    invalidateToken();
    boot();
  }, [boot]);

  useEffect(() => {
    boot();
  }, [boot]);

  useEffect(() => {
    if (!session || session === "error" || session === "missing") return;
    return startHeartbeat(session);
  }, [session]);

  useEffect(() => {
    if (!config) return;
    const bump = () => {
      lastActive.current = Date.now();
    };
    for (const ev of ["pointerdown", "keydown"]) window.addEventListener(ev, bump);
    const timer = setInterval(() => {
      if (Date.now() - lastActive.current > IDLE_MS) {
        setRoute((prev) => nextRoute(prev, "idle"));
      }
    }, 5_000);
    return () => {
      for (const ev of ["pointerdown", "keydown"]) window.removeEventListener(ev, bump);
      clearInterval(timer);
    };
  }, [config]);

  useEffect(() => {
    document.documentElement.style.fontSize = a11y ? "125%" : "100%";
    if (a11y) document.documentElement.dataset.contrast = "high";
    else delete document.documentElement.dataset.contrast;
    try {
      localStorage.setItem("sage_screen_a11y", a11y ? "1" : "0");
    } catch {
      /* 存储不可用时仅本次会话生效 */
    }
  }, [a11y]);

  const go = useCallback(
    (action: KioskAction, seed = "") => {
      lastActive.current = Date.now();
      if (action === "ask") setChatSeed(seed);
      setRoute((prev) => nextRoute(prev, action));
    },
    [],
  );

  if (!config || session === "missing") {
    return (
      <KioskShell>
        <LoadError detail="缺少 VITE_SCREEN_USERNAME / VITE_SCREEN_PASSWORD 配置" />
      </KioskShell>
    );
  }
  if (session === null) {
    return (
      <KioskShell>
        <div className="flex h-full items-center justify-center">
          <Spinner label="大屏启动中" />
        </div>
      </KioskShell>
    );
  }
  if (session === "error") {
    return (
      <KioskShell>
        <div className="flex h-full items-center justify-center">
          <LoadError detail={error || "设备登录失败"} onRetry={boot} />
        </div>
      </KioskShell>
    );
  }

  return (
    <>
      {route === "home" && (
        <Home session={session} onAsk={go} onAuthLost={onAuthLost} />
      )}
      {route === "chat" && (
        <Chat session={session} seed={chatSeed} onBack={() => go("home")}
              onRoute={(p) => { setRoutePayload(p); go("route"); }} />
      )}
      {route === "route" && (
        <RoutePage session={session} payload={routePayload!} onBack={() => go("home")} />
      )}
      <button
        onClick={() => setA11y((v) => !v)}
        title="无障碍模式：放大字号并提高对比度"
        className={`fixed bottom-5 right-5 z-40 flex items-center gap-2 rounded-full border px-6 py-3 text-xl shadow-xl
                    ${a11y ? "border-accent-deep bg-accent text-ink" : "border-rule bg-paper-2 text-ink-2"}`}>
        <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden className="size-5"><path d="M12 2a2 2 0 0 1 2 2 2 2 0 0 1-2 2 2 2 0 0 1-2-2 2 2 0 0 1 2-2m11 7h-7v12h-2v-6h-2v6H10V9H3V7h20v2Z"/></svg>
        无障碍{a11y ? "开" : "关"}
      </button>
    </>
  );
}
