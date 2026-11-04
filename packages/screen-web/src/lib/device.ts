/** 设备会话：环境凭据登录 → token/claims 缓存 → /devices/me 自读身份。 */

import { ApiError, apiFetch } from "@sage/map-render/src/lib/http/api.ts";

const TOKEN_KEY = "sage_screen_token";

export interface DeviceIdentity {
  token: string;
  tenantId: number;
  venueId: number;
  deviceId: number;
  deviceName: string;
  deviceCode: string;
  venueName: string;
  businessHours: string | null;
  floorId: number | null;
  floorName: string | null;
  positionX: number | null;
  positionY: number | null;
}

export interface ScreenConfig {
  username: string;
  password: string;
  venueId: number;
}

export function readScreenConfig(): ScreenConfig | null {
  const username = import.meta.env.VITE_SCREEN_USERNAME as string | undefined;
  const password = import.meta.env.VITE_SCREEN_PASSWORD as string | undefined;
  const venueId = Number(import.meta.env.VITE_VENUE_ID ?? 1);
  if (!username || !password) return null;
  return { username, password, venueId: Number.isFinite(venueId) ? venueId : 1 };
}

/** JWT payload 解码（TextDecoder 保证 CJK 不乱码）。 */
export function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const part = token.split(".")[1];
    const b64 = part.replace(/-/g, "+").replace(/_/g, "/");
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    return JSON.parse(new TextDecoder().decode(bytes));
  } catch {
    return null;
  }
}

function cachedToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

function cacheToken(token: string): void {
  try {
    sessionStorage.setItem(TOKEN_KEY, token);
  } catch {
    /* 隐私模式等存储不可用：退化为每次重登 */
  }
}

export function invalidateToken(): void {
  try {
    sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* 同上 */
  }
}

export async function deviceLogin(config: ScreenConfig): Promise<DeviceIdentity> {
  let token: string | null = cachedToken();
  let claims = token ? decodeJwtPayload(token) : null;
  const usable = !!claims && (claims.exp as number) * 1000 >= Date.now() + 30_000
    && claims.device_id != null;
  if (!usable) {
    const resp = await apiFetch<{ access_token: string; device_id: number | null }>(
      "/api/v1/auth/login",
      { method: "POST", body: JSON.stringify({
        tenant_code: "shanqueli-demo", username: config.username,
        password: config.password,
      }) },
    );
    token = resp.access_token;
    cacheToken(token);
    const fresh = decodeJwtPayload(token);
    if (!fresh) throw new ApiError(500, null, "登录响应 token 无法解析");
    claims = fresh;
  }
  if (!token) throw new ApiError(500, null, "登录态异常");
  if (!claims) throw new ApiError(500, null, "登录态异常");
  const deviceId = (claims.device_id as number | null) ?? null;
  if (deviceId == null) throw new ApiError(500, null, "登录响应缺 device_id");
  const me = await apiFetch<{
    data: { code: string; name: string; venue_id: number;
            venue_name: string; business_hours: string | null;
            floor_id: number | null; floor_name: string | null;
            position_x: number | null; position_y: number | null };
  }>("/api/v1/devices/me", { token });
  return {
    token, tenantId: claims.tenant_id as number, venueId: me.data.venue_id,
    deviceId, deviceName: me.data.name, deviceCode: me.data.code,
    venueName: me.data.venue_name, businessHours: me.data.business_hours,
    floorId: me.data.floor_id, floorName: me.data.floor_name,
    positionX: me.data.position_x, positionY: me.data.position_y,
  };
}

export const APP_VERSION = "screen-web-0.1.0";

/** 设备心跳（F-19）：启动即报一次，其后每 60s；失败静默（下轮补报）。 */
export function startHeartbeat(identity: DeviceIdentity): () => void {
  const beat = async () => {
    try {
      await apiFetch(`/api/v1/devices/${identity.deviceId}/heartbeat`, {
        method: "POST",
        token: identity.token,
        body: JSON.stringify({ status: "online", app_version: APP_VERSION }),
      });
    } catch {
      /* 心跳失败不打扰展示；设备状态由下轮修正 */
    }
  };
  void beat();
  const timer = setInterval(beat, 60_000);
  return () => clearInterval(timer);
}
