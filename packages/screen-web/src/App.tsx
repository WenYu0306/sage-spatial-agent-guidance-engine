/** 大屏 App：设备会话引导 + kiosk 路由状态机 + 闲置回首页。 */

import { useCallback, useEffect, useRef, useState } from "react";
import { KioskShell, LoadError, Spinner } from "./components/ui.tsx";
import { Chat } from "./pages/Chat.tsx";
import { Home } from "./pages/Home.tsx";
import {
  deviceLogin,
  invalidateToken,
  readScreenConfig,
  type DeviceIdentity,
} from "./lib/device.ts";
import { IDLE_MS, nextRoute, type KioskAction, type KioskRoute } from "./lib/kiosk.ts";

export function App() {
  const config = readScreenConfig();
  const [session, setSession] = useState<DeviceIdentity | null | "error" | "missing">(
    config ? null : "missing",
  );
  const [error, setError] = useState("");
  const [route, setRoute] = useState<KioskRoute>("home");
  const [chatSeed, setChatSeed] = useState("");
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
        <Chat session={session} seed={chatSeed} onBack={() => go("home")} />
      )}
      {route === "route" && (
        <KioskShell>
          <button onClick={() => go("home")}
            className="self-start rounded-lg bg-slate-800 px-6 py-2 text-xl">
            ← 返回首页
          </button>
          <div className="flex flex-1 items-center justify-center text-2xl text-slate-500">
            路线展示页（④ 提交实现）
          </div>
        </KioskShell>
      )}
    </>
  );
}
