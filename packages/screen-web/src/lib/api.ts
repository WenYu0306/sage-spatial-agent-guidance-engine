/** 统一 fetch：错误信封解包 + 401 信号（device.ts 负责重登）。 */

export class ApiError extends Error {
  status: number;
  code: number | null;

  constructor(status: number, code: number | null, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export async function apiFetch<T>(
  path: string,
  init?: RequestInit & { token?: string | null },
): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.token) headers.set("Authorization", `Bearer ${init.token}`);
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  let resp: Response;
  try {
    resp = await fetch(path, { ...init, headers });
  } catch (cause) {
    throw new ApiError(0, null, "网络不可达");
  }
  if (resp.status === 401) throw new ApiError(401, 1001, "登录失效");
  const text = await resp.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = null;
  }
  if (!resp.ok) {
    const b = body as { error_code?: number; message?: string } | null;
    throw new ApiError(resp.status, b?.error_code ?? null, b?.message ?? `HTTP ${resp.status}`);
  }
  return body as T;
}
