/** 活动管理：列表过滤 + 状态机按钮（角色矩阵）+ 新建（merchant 自动绑锚点门店）。 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, ApiError } from "../lib/api.ts";
import { decodeJwtPayload, profileStore, tokenStore } from "../lib/auth.ts";
import { ACT_STATUS_ZH, ACT_TYPE_ZH, availableActActions, type ActStatus } from "../lib/actActions.ts";
import { Badge, Button, Empty, Input, LoadError, Select, Spinner, Table, useToast } from "../components/ui.tsx";

type Activity = {
  id: number; venue_id: number; poi_id: number | null; act_type: string;
  title: string; status: ActStatus; start_at: string; end_at: string;
};

export default function ActivitiesPage() {
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const list = useQuery({
    queryKey: ["activities", status, page],
    queryFn: () => api<{ items: Activity[]; total: number }>(
      `/api/v1/activities?page=${page}&page_size=10${status ? `&status=${status}` : ""}`),
    retry: 1,
  });
  const roles = profileStore()?.get === undefined ? [] : (profileStore().get()?.roles ?? []);
  const merchantId = decodeJwtPayload(tokenStore().get() ?? "")?.merchant_id ?? null;
  const canCreate = ["platform_admin", "venue_admin", "venue_editor", "merchant"]
    .some((r) => roles.includes(r));

  return (
    <div>
      <div className="mb-4 flex items-center gap-2">
        <Select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
          <option value="">全部状态</option>
          {Object.entries(ACT_STATUS_ZH).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </Select>
        {canCreate && <Button size="sm" onClick={() => setCreating(true)}>＋ 新建活动</Button>}
      </div>
      {list.isPending && <Spinner />}
      {list.isError && <LoadError error={list.error} onRetry={() => void list.refetch()} />}
      {list.data && list.data.items.length === 0 && <Empty text="暂无活动" />}
      {list.data && list.data.items.length > 0 && (
        <Table head={["标题", "类型", "门店", "状态", "时间窗", "操作"]}>
          {list.data.items.map((a) => (
            <tr key={a.id} className="border-b border-slate-100">
              <td className="px-3 py-2 font-medium text-slate-700">{a.title}</td>
              <td className="px-3 py-2 text-slate-500">{ACT_TYPE_ZH[a.act_type] ?? a.act_type}</td>
              <td className="px-3 py-2 text-xs text-slate-400">{a.poi_id ? `#${a.poi_id}` : "商场级"}</td>
              <td className="px-3 py-2"><Badge tone={a.status === "active" ? "green" : "slate"}>{ACT_STATUS_ZH[a.status]}</Badge></td>
              <td className="px-3 py-2 text-xs text-slate-400">
                {a.start_at.slice(5, 16)} ~ {a.end_at.slice(5, 16)}
              </td>
              <td className="px-3 py-2">
                <div className="flex gap-1.5">
                  {availableActActions(a.status, roles).map((act) => (
                    <ActPublish key={act.target} id={a.id} title={a.title} target={act.target}
                      label={act.label} kind={act.kind} onDone={() => void list.refetch()} />
                  ))}
                </div>
              </td>
            </tr>
          ))}
        </Table>
      )}
      <div className="mt-4 flex justify-end gap-2 text-sm">
        <Button kind="ghost" size="sm" disabled={page <= 1} onClick={() => setPage((n) => n - 1)}>上一页</Button>
        <Button kind="ghost" size="sm" disabled={page >= Math.max(1, Math.ceil((list.data?.total ?? 0) / 10))}
          onClick={() => setPage((n) => n + 1)}>下一页</Button>
      </div>
      {creating && (
        <CreateActModal merchantId={merchantId} onClose={() => setCreating(false)}
          onSaved={() => { setCreating(false); void list.refetch(); }} />
      )}
    </div>
  );
}

function ActPublish({ id, title, target, label, kind, onDone }: {
  id: number; title: string; target: string; label: string;
  kind: "primary" | "ghost" | "danger"; onDone: () => void;
}) {
  const toast = useToast();
  const mutation = useMutation({
    mutationFn: () => api(`/api/v1/activities/${id}/publish`,
      { method: "POST", body: JSON.stringify({ target }) }),
    onSuccess: () => { toast("ok", `${title} → ${label}`); onDone(); },
    onError: (e) => toast("err", e instanceof ApiError ? e.message : "操作失败"),
  });
  return <Button size="sm" kind={kind} disabled={mutation.isPending}
    onClick={() => mutation.mutate()}>{mutation.isPending ? "…" : label}</Button>;
}

function CreateActModal({ merchantId, onClose, onSaved }: {
  merchantId: number | null; onClose: () => void; onSaved: () => void;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    title: "", act_type: "shop_promo",
    start_at: new Date().toISOString().slice(0, 16),
    end_at: new Date(Date.now() + 86400_000).toISOString().slice(0, 16),
  });
  const [err, setErr] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: () => api("/api/v1/activities", {
      method: "POST",
      body: JSON.stringify({
        title: form.title, act_type: form.act_type,
        start_at: new Date(form.start_at).toISOString(),
        end_at: new Date(form.end_at).toISOString(),
        ...(merchantId != null ? { poi_id: merchantId } : {}),
      }),
    }),
    onSuccess: () => { toast("ok", "活动已创建（草稿）"); void queryClient.invalidateQueries({ queryKey: ["activities"] }); onSaved(); },
    onError: (e) => setErr(e instanceof ApiError ? e.message : "创建失败"),
  });
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="w-[440px] rounded-xl bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <h3 className="mb-4 text-base font-semibold text-slate-800">
          新建活动{merchantId != null ? `（绑定门店 #${merchantId}）` : ""}
        </h3>
        <label className="mb-1 block text-xs text-slate-500">标题</label>
        <Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
        <label className="mb-1 mt-3 block text-xs text-slate-500">类型</label>
        <Select value={form.act_type} onChange={(e) => setForm({ ...form, act_type: e.target.value })}>
          {Object.entries(ACT_TYPE_ZH).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </Select>
        <div className="mt-3 grid grid-cols-2 gap-2">
          <div>
            <label className="mb-1 block text-xs text-slate-500">开始</label>
            <Input type="datetime-local" value={form.start_at}
              onChange={(e) => setForm({ ...form, start_at: e.target.value })} />
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-500">结束</label>
            <Input type="datetime-local" value={form.end_at}
              onChange={(e) => setForm({ ...form, end_at: e.target.value })} />
          </div>
        </div>
        {err && <p className="mt-3 rounded bg-red-50 p-2 text-xs text-red-600">{err}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <Button kind="ghost" onClick={onClose}>取消</Button>
          <Button disabled={!form.title.trim() || create.isPending} onClick={() => create.mutate()}>
            {create.isPending ? "创建中…" : "创建"}
          </Button>
        </div>
      </div>
    </div>
  );
}
