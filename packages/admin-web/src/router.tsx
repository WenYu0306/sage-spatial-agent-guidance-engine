/** hash 路由（D-023：不引 router 框架；登录守卫在 App 声明式处理）。 */
import { useEffect, useState } from "react";

import { tokenStore } from "./lib/auth.ts";

export function useHashRoute(): string {
  const [hash, setHash] = useState(() => globalThis.location?.hash ?? "#/venues");
  useEffect(() => {
    const onChange = () => setHash(globalThis.location.hash || "#/venues");
    globalThis.addEventListener?.("hashchange", onChange);
    return () => globalThis.removeEventListener?.("hashchange", onChange);
  }, []);
  return hash.replace(/^#/, "") || "/venues";
}

export function navigate(path: string): void {
  globalThis.location.hash = `#${path}`;
}


