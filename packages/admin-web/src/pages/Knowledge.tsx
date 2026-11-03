/** 知识内容管理：列表 + 创建/编辑（版本自增展示）+ 删除；merchant 服务端 403，前端隐藏入口。 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, ApiError } from "../lib/api.ts";
import { profileStore } from "../lib/auth.ts";
import { Badge, Button, Empty, Input, LoadError, Spinner, Table, useToast } from "../components/ui.tsx";

type Doc = { id: number; doc_type: string; title: string; status: string; version: number };

export default function KnowledgePage() {
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<Doc | null>(null);
  const list = useQuery({
    queryKey: ["docs", page],
    queryFn: () => api<{ items: Doc[]; total: number }>(
      `/api/v1/knowledge-documents?page=${page}&page_size=10`),
    retry: 1,
  });
  const roles = profileStore().get?.()?.roles ?? [];
  const canWrite = ["platform_admin", "venue_admin", "venue_editor"].some((r) => roles.includes(r));
  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <p className="text-xs text-slate-400">
          文档改动后需经 M6 重嵌索引才会进入 AI 问答（增量 ingest 为后续任务）
        </p>
        {canWrite && <Button size="sm" onClick={() => setEditing({ id: 0, doc_type: "faq", title: "", status: "active", version: 1 })}>＋ 新建文档</Button>}
      </div>
      {list.isPending && <Spinner />}
      {list.isError && <LoadError error={list.error} onRetry={() => void list.refetch()} />}
      {list.data && list.data.items.length === 0 && <Empty text="暂无知识文档" />}
      {list.data && list.data.items.length > 0 && (
        <>
          <Table head={["标题", "类型", "状态", "版本", "操作"]}>
            {list.data.items.map((d) => (
              <tr key={d.id} className="border-b border-slate-100">
                <td className="px-3 py-2 font-medium text-slate-700">{d.title}</td>
                <td className="px-3 py-2 text-slate-500">{d.doc_type}</td>
                <td className="px-3 py-2"><Badge tone={d.status === "active" ? "green" : "slate"}>{d.status}</Badge></td>
                <td className="px-3 py-2 text-slate-400">v{d.version}</td>
                <td className="px-3 py-2">
                  {canWrite && (
                    <div className="flex gap-1.5">
                      <Button size="sm" kind="ghost" onClick={() => setEditing(d)}>编辑</Button>
                      <DeleteDoc id={d.id} title={d.title} onDone={() => void list.refetch()} />
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </Table>
          <div className="mt-4 flex justify-end gap-2 text-sm">
            <Button kind="ghost" size="sm" disabled={page <= 1} onClick={() => setPage((n) => n - 1)}>上一页</Button>
            <Button kind="ghost" size="sm"
              disabled={page >= Math.max(1, Math.ceil((list.data.total) / 10))}
              onClick={() => setPage((n) => n + 1)}>下一页</Button>
          </div>
        </>
      )}
      {editing && (
        <DocModal doc={editing} onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); void list.refetch(); }} />
      )}
    </div>
  );
}

function DeleteDoc({ id, title, onDone }: { id: number; title: string; onDone: () => void }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => api(`/api/v1/knowledge-documents/${id}`, { method: "DELETE" }),
    onSuccess: () => { toast("ok", `${title} 已删除`); void queryClient.invalidateQueries({ queryKey: ["docs"] }); onDone(); },
    onError: (e) => toast("err", e instanceof ApiError ? e.message : "删除失败"),
  });
  return <Button size="sm" kind="danger" disabled={mutation.isPending}
    onClick={() => mutation.mutate()}>{mutation.isPending ? "…" : "删除"}</Button>;
}

function DocModal({ doc, onClose, onSaved }: {
  doc: Doc; onClose: () => void; onSaved: () => void;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const isNew = doc.id === 0;
  const [form, setForm] = useState({
    title: doc.title, doc_type: doc.doc_type,
    content: isNew ? "" : "（载入中…）",
  });
  const [err, setErr] = useState<string | null>(null);
  const detail = useQuery({
    queryKey: ["doc", doc.id],
    queryFn: () => api<{ content: string; title: string }>(`/api/v1/knowledge-documents/${doc.id}`),
    enabled: !isNew,
  });
  if (!isNew && detail.data && form.content === "（载入中…）") {
    setForm({ title: detail.data.title, doc_type: form.doc_type, content: detail.data.content });
  }
  const save = useMutation({
    mutationFn: () => {
      if (isNew) {
        return api("/api/v1/knowledge-documents", {
          method: "POST",
          body: JSON.stringify({ venue_id: 0, doc_type: form.doc_type, title: form.title, content: form.content }),
        });
      }
      return api(`/api/v1/knowledge-documents/${doc.id}`, {
        method: "PATCH",
        body: JSON.stringify({ title: form.title, content: form.content }),
      });
    },
    onSuccess: () => {
      toast("ok", isNew ? "文档已创建" : "文档已更新（版本 +1）");
      void queryClient.invalidateQueries({ queryKey: ["docs"] });
      onSaved();
    },
    onError: (e) => setErr(e instanceof ApiError ? e.message : "保存失败"),
  });
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="flex max-h-[85vh] w-[560px] flex-col rounded-xl bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <h3 className="mb-4 text-base font-semibold text-slate-800">
          {isNew ? "新建知识文档" : `编辑文档 #${doc.id}（当前 v${doc.version}）`}
        </h3>
        <label className="mb-1 block text-xs text-slate-500">标题</label>
        <Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
        <label className="mb-1 mt-3 block text-xs text-slate-500">类型</label>
        <Input value={form.doc_type} onChange={(e) => setForm({ ...form, doc_type: e.target.value })} />
        <label className="mb-1 mt-3 block text-xs text-slate-500">内容</label>
        <textarea
          value={form.content}
          onChange={(e) => setForm({ ...form, content: e.target.value })}
          rows={8}
          className="w-full rounded-md border border-slate-300 p-2 text-sm outline-none focus:border-slate-500"
        />
        {err && <p className="mt-3 rounded bg-red-50 p-2 text-xs text-red-600">{err}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <Button kind="ghost" onClick={onClose}>取消</Button>
          <Button disabled={!form.title.trim() || !form.content.trim() || save.isPending}
            onClick={() => save.mutate()}>
            {save.isPending ? "保存中…" : "保存"}
          </Button>
        </div>
      </div>
    </div>
  );
}
