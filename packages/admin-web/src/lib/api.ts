/** M10 API 客户端：token 注入、业务错误包络 → ApiError、401 统一登出回调。 */

import { tokenStore } from "./auth.ts";

export class ApiError extends Error {
  status: number;
  error_code: number | null;

  constructor(status: number, error_code: number | null, message: string) {
    super(message);
    this.status = status;
    this.error_code = error_code;
  }
}

let onUnauthorized: (() => void) | null = null;

export function setUnauthorizedHandler(fn: () => void): void {
  onUnauthorized = fn;
}

export async function mapResponse<T>(resp: Response): Promise<T> {
  const text = await resp.text();
  const body: unknown = text ? JSON.parse(text) : {};
  if (!resp.ok) {
    const err = body as { error_code?: number; message?: string };
    if (resp.status === 401) onUnauthorized?.();
    throw new ApiError(resp.status, err.error_code ?? null, err.message ?? `HTTP ${resp.status}`);
  }
  const err = body as { error_code?: number; message?: string };
  if (err.error_code) {
    throw new ApiError(resp.status, err.error_code, err.message ?? "业务错误");
  }
  return body as T;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = tokenStore().get();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  let resp: Response;
  try {
    resp = await fetch(path, { ...init, headers });
  } catch {
    throw new ApiError(0, null, "网络不可达，请检查服务是否启动");
  }
  return mapResponse<T>(resp);
}
