/** 游客身份（PRD 2.3：anonymous_id 标识，无登录）。 */

const ANON_KEY = "sage_mobile_anon";

export function anonymousId(): string {
  try {
    const existing = localStorage.getItem(ANON_KEY);
    if (existing) return existing;
    const fresh = crypto.randomUUID();
    localStorage.setItem(ANON_KEY, fresh);
    return fresh;
  } catch {
    return "anonymous-fallback";
  }
}
