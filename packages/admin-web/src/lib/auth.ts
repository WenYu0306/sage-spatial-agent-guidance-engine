/** M10 认证前端件：token 存储（可注入）、JWT payload 解码（仅展示用）、角色判断。 */

export type JwtPayload = {
  sub: string;
  tenant_id: number;
  roles: string[];
  venue_id: number | null;
  merchant_id: number | null;
  display_name?: string;
};

type StorageLike = {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
};

const TOKEN_KEY = "sage_admin_token";

export function tokenStore(storage: StorageLike | undefined = undefined) {
  const impl: StorageLike =
    storage ?? (globalThis as { localStorage?: StorageLike }).localStorage ??
    { getItem: () => null, setItem: () => undefined, removeItem: () => undefined };
  return {
    get(): string | null {
      return impl.getItem(TOKEN_KEY);
    },
    set(token: string): void {
      impl.setItem(TOKEN_KEY, token);
    },
    clear(): void {
      impl.removeItem(TOKEN_KEY);
    },
  };
}

export function decodeJwtPayload(token: string): JwtPayload | null {
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  try {
    const json = atob(parts[1].replace(/-/g, "+").replace(/_/g, "/"));
    return JSON.parse(decodeURIComponent(escape(json))) as JwtPayload;
  } catch {
    return null;
  }
}

export function isRoleAllowed(userRoles: string[], needed: string[]): boolean {
  if (needed.length === 0) return true;
  return userRoles.some((r) => needed.includes(r));
}

const PROFILE_KEY = "sage_admin_profile";

export type AdminProfile = { display_name: string; roles: string[] };

export function profileStore(storage: StorageLike | undefined = undefined) {
  const impl: StorageLike =
    storage ?? (globalThis as { localStorage?: StorageLike }).localStorage ??
    { getItem: () => null, setItem: () => undefined, removeItem: () => undefined };
  return {
    get(): AdminProfile | null {
      const raw = impl.getItem(PROFILE_KEY);
      if (!raw) return null;
      try {
        return JSON.parse(raw) as AdminProfile;
      } catch {
        return null;
      }
    },
    set(profile: AdminProfile): void {
      impl.setItem(PROFILE_KEY, JSON.stringify(profile));
    },
    clear(): void {
      impl.removeItem(PROFILE_KEY);
    },
  };
}
