/** 登录页：对接 POST /api/v1/auth/login（content-service）。 */
import { useState } from "react";

import { api } from "../lib/api.ts";
import { profileStore, tokenStore } from "../lib/auth.ts";
import { navigate } from "../router.tsx";
import { Button, Input, useToast } from "../components/ui.tsx";
import { validateLoginForm } from "../lib/validate.ts";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [tenantCode, setTenantCode] = useState("shanqueli-demo");
  const [submitting, setSubmitting] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<{ field: string; message: string }[]>([]);
  const [apiError, setApiError] = useState<string | null>(null);
  const toast = useToast();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setApiError(null);
    const errs = validateLoginForm(username, password);
    setFieldErrors(errs);
    if (errs.length > 0) return;
    setSubmitting(true);
    try {
      const body = await api<{ access_token: string; display_name: string; roles: string[] }>(
        "/api/v1/auth/login",
        { method: "POST", body: JSON.stringify({ tenant_code: tenantCode, username, password }) },
      );
      tokenStore().set(body.access_token);
      profileStore().set({ display_name: body.display_name, roles: body.roles });
      toast("ok", `欢迎，${body.display_name}`);
      navigate("/venues");
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "登录失败");
    } finally {
      setSubmitting(false);
    }
  }

  const errOf = (field: string) => fieldErrors.find((e) => e.field === field)?.message;

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100">
      <form onSubmit={submit} className="w-96 rounded-xl bg-white p-8 shadow-md">
        <h1 className="mb-1 text-xl font-semibold text-slate-800">山雀里·栖云广场</h1>
        <p className="mb-6 text-sm text-slate-400">运营后台（M10）</p>
        <label className="mb-1 block text-xs text-slate-500">租户编码</label>
        <Input value={tenantCode} onChange={(e) => setTenantCode(e.target.value)} className="mb-4" />
        <label className="mb-1 block text-xs text-slate-500">用户名</label>
        <Input value={username} onChange={(e) => setUsername(e.target.value)} className="mb-1" />
        {errOf("username") && <p className="mb-1 text-xs text-red-600">{errOf("username")}</p>}
        <label className="mb-1 mt-3 block text-xs text-slate-500">口令</label>
        <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} className="mb-1" />
        {errOf("password") && <p className="mb-1 text-xs text-red-600">{errOf("password")}</p>}
        {apiError && <p className="mt-3 rounded bg-red-50 p-2 text-xs text-red-600">{apiError}</p>}
        <Button type="submit" disabled={submitting} className="mt-5 w-full">
          {submitting ? "登录中…" : "登录"}
        </Button>
        <p className="mt-4 text-xs text-slate-400">演示账号 demo_admin / 口令见 SEED_DEMO_ADMIN_PASSWORD</p>
      </form>
    </div>
  );
}
