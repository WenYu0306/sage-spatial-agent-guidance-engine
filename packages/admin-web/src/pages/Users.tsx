/** 账号与角色（platform_admin/venue_admin）：列表 + 新建（角色字典）+ 禁用。 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, ApiError } from "../lib/api.ts";
import { Badge, Button, Empty, Input, LoadError, Select, Spinner, Table, useToast } from "../components/ui.tsx";

type UserRow = {
  id: number; username: string; display_name: string; status: string;
  last_login_at: string | null; roles: string[];
};
const ROLE_ZH: Record<string, string> = {
  platform_admin: "平台管理员", venue_admin: "运营管理员",
  venue_editor: "运营编辑", merchant: "商户", device: "设备",
};

export default function UsersPage() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [creating, setCreating] = useState(false);
  const list = useQuery({
    queryKey: ["users"],
    queryFn: () => api<{ items: UserRow[] }>("/api/v1/users"),
    retry: 1,
  });
  const disable = useMutation({
    mutationFn: (u: UserRow) => api(`/api/v1/users/${u.id}`, {
      method: "PATCH",
      body: JSON.stringify({ status: u.status === "active" ? "disabled" : "active" }),
    }),
    onSuccess: (r) => {
      toast("ok", `账号已${(r as { status: string }).status === "disabled" ? "禁用" : "启用"}`);
      void queryClient.invalidateQueries({ queryKey: ["users"] });
    },
    onError: (e) => toast("err", e instanceof ApiError ? e.message : "操作失败"),
  });
  return (
    <div>
      <div className="mb-4">
        <Button size="sm" onClick={() => setCreating(true)}>＋ 新建账号</Button>
      </div>
      {list.isPending && <Spinner />}
      {list.isError && <LoadError error={list.error} onRetry={() => void list.refetch()} />}
      {list.data && list.data.items.length === 0 && <Empty text="暂无账号" />}
      {list.data && (
        <Table head={["用户名", "显示名", "角色", "状态", "最近登录", "操作"]}>
          {list.data.items.map((u) => (
            <tr key={u.id} className="border-b border-slate-100">
              <td className="px-3 py-2 font-medium text-slate-700">{u.username}</td>
              <td className="px-3 py-2 text-slate-500">{u.display_name}</td>
              <td className="px-3 py-2">
                <div className="flex gap-1">
                  {u.roles.map((r) => <Badge key={r} tone="blue">{ROLE_ZH[r] ?? r}</Badge>)}
                </div>
              </td>
              <td className="px-3 py-2">
                <Badge tone={u.status === "active" ? "green" : "red"}>
                  {u.status === "active" ? "启用" : "禁用"}
                </Badge>
              </td>
              <td className="px-3 py-2 text-xs text-slate-400">
                {u.last_login_at ? u.last_login_at.slice(0, 16).replace("T", " ") : "从未"}
              </td>
              <td className="px-3 py-2">
                <Button size="sm" kind={u.status === "active" ? "danger" : "ghost"}
                  disabled={disable.isPending} onClick={() => disable.mutate(u)}>
                  {u.status === "active" ? "禁用" : "启用"}
                </Button>
              </td>
            </tr>
          ))}
        </Table>
      )}
      {creating && (
        <CreateUserModal onClose={() => setCreating(false)} onSaved={() => {
          setCreating(false);
          void queryClient.invalidateQueries({ queryKey: ["users"] });
        }} />
      )}
    </div>
  );
}

function CreateUserModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const toast = useToast();
  const [form, setForm] = useState({
    username: "", display_name: "", role: "venue_editor", password: "",
  });
  const [err, setErr] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: () => api("/api/v1/users", {
      method: "POST", body: JSON.stringify(form),
    }),
    onSuccess: () => { toast("ok", "账号已创建"); onSaved(); },
    onError: (e) => setErr(e instanceof ApiError ? e.message : "创建失败"),
  });
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="w-[420px] rounded-xl bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <h3 className="mb-4 text-base font-semibold text-slate-800">新建账号</h3>
        <label className="mb-1 block text-xs text-slate-500">用户名</label>
        <Input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
        <label className="mb-1 mt-3 block text-xs text-slate-500">显示名</label>
        <Input value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
        <label className="mb-1 mt-3 block text-xs text-slate-500">角色</label>
        <Select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
          {["venue_admin", "venue_editor", "merchant"].map((r) => (
            <option key={r} value={r}>{ROLE_ZH[r]}</option>
          ))}
        </Select>
        <label className="mb-1 mt-3 block text-xs text-slate-500">初始口令（≥8 位）</label>
        <Input type="password" value={form.password}
          onChange={(e) => setForm({ ...form, password: e.target.value })} />
        {err && <p className="mt-3 rounded bg-red-50 p-2 text-xs text-red-600">{err}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <Button kind="ghost" onClick={onClose}>取消</Button>
          <Button disabled={!form.username || !form.display_name || form.password.length < 8 || create.isPending}
            onClick={() => create.mutate()}>
            {create.isPending ? "创建中…" : "创建"}
          </Button>
        </div>
      </div>
    </div>
  );
}
