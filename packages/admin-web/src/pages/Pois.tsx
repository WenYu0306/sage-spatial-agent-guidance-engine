/** POI 管理：组合过滤列表 + 编辑（校验/toast）+ 发布状态机按钮 + 坐标拾取（复用 map-render FloorPlan）。 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { FloorPlan, type MapMarker } from "@sage/map-render/src/poipicker/FloorPlan.tsx";

import { api, ApiError } from "../lib/api.ts";
import { profileStore } from "../lib/auth.ts";
import { availableActions, buildPoiQuery, type PoiStatus, type PoiTarget } from "../lib/poiActions.ts";
import { validatePoiForm, type FieldError } from "../lib/validate.ts";
import {
  Badge, Button, Empty, Input, LoadError, Select, Spinner, Table, useToast,
} from "../components/ui.tsx";

type Poi = {
  id: number; name: string; category_code: string; floor_id: number;
  merchant_id: number | null; position_x: number; position_y: number;
  status: PoiStatus; tags: string[]; intro: string | null;
};
type ListBody = { items: Poi[]; total: number };
type Category = { code: string; name: string; is_facility: boolean };
type Floor = { id: number; name: string; level: number };

const STATUS_TONE: Record<PoiStatus, string> = {
  draft: "slate", pending: "amber", published: "green", offline: "red",
};
const STATUS_ZH: Record<PoiStatus, string> = {
  draft: "草稿", pending: "待审核", published: "已发布", offline: "已下架",
};

export default function PoisPage() {
  const [keyword, setKeyword] = useState("");
  const [category, setCategory] = useState("");
  const [floorId, setFloorId] = useState<string>("");
  const [status, setStatus] = useState("");
  const [openNow, setOpenNow] = useState(false);
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<Poi | null>(null);
  const pageSize = 10;

  const qs = buildPoiQuery({
    keyword, category, floorId: floorId ? Number(floorId) : null,
    status, openNow, page, pageSize,
  });
  const list = useQuery({
    queryKey: ["pois", qs],
    queryFn: () => api<ListBody>(`/api/v1/pois?${qs}`),
    retry: 1,
  });
  const categories = useQuery({
    queryKey: ["categories"],
    queryFn: () => api<{ items: Category[] }>("/api/v1/categories"),
    staleTime: 60_000,
  });
  const floors = useQuery({
    queryKey: ["floors", 0],
    queryFn: async () => {
      const venues = await api<{ items: { id: number }[] }>("/api/v1/venues");
      return api<{ items: Floor[] }>(`/api/v1/venues/${venues.items[0]?.id}/floors`);
    },
    staleTime: 60_000,
  });

  const roles = profileStore().get()?.roles ?? [];
  const totalPages = list.data ? Math.max(1, Math.ceil(list.data.total / pageSize)) : 1;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Input
          placeholder="名称/简介关键词" value={keyword}
          onChange={(e) => { setKeyword(e.target.value); setPage(1); }} className="!w-44"
        />
        <Select value={category} onChange={(e) => { setCategory(e.target.value); setPage(1); }}>
          <option value="">全部分类</option>
          {(categories.data?.items ?? []).filter((c) => !c.is_facility).map((c) => (
            <option key={c.code} value={c.code}>{c.name}</option>
          ))}
        </Select>
        <Select value={floorId} onChange={(e) => { setFloorId(e.target.value); setPage(1); }}>
          <option value="">全部楼层</option>
          {(floors.data?.items ?? []).map((f) => (
            <option key={f.id} value={f.id}>{f.name}</option>
          ))}
        </Select>
        <Select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
          <option value="">全部状态</option>
          {Object.entries(STATUS_ZH).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </Select>
        <label className="flex items-center gap-1 text-sm text-slate-600">
          <input type="checkbox" checked={openNow}
            onChange={(e) => { setOpenNow(e.target.checked); setPage(1); }} /> 营业中
        </label>
        <span className="ml-auto text-xs text-slate-400">共 {list.data?.total ?? "…"} 条</span>
      </div>

      {list.isPending && <Spinner />}
      {list.isError && <LoadError error={list.error} onRetry={() => void list.refetch()} />}
      {list.data && list.data.items.length === 0 && <Empty text="没有符合条件的 POI" />}
      {list.data && list.data.items.length > 0 && (
        <>
          <Table head={["名称", "分类", "楼层", "状态", "坐标", "操作"]}>
            {list.data.items.map((p) => (
              <tr key={p.id} className="border-b border-slate-100 hover:bg-slate-50">
                <td className="px-3 py-2 font-medium text-slate-700">{p.name}</td>
                <td className="px-3 py-2 text-slate-500">{categories.data?.items.find((c) => c.code === p.category_code)?.name ?? p.category_code}</td>
                <td className="px-3 py-2 text-slate-500">
                  {floors.data?.items.find((f) => f.id === p.floor_id)?.name ?? p.floor_id}
                </td>
                <td className="px-3 py-2">
                  <Badge tone={STATUS_TONE[p.status]}>{STATUS_ZH[p.status]}</Badge>
                </td>
                <td className="px-3 py-2 text-xs text-slate-400">
                  {p.position_x}, {p.position_y}
                </td>
                <td className="px-3 py-2">
                  <div className="flex gap-1.5">
                    <Button size="sm" kind="ghost" onClick={() => setEditing(p)}>编辑</Button>
                    {availableActions(p.status, roles).map((a) => (
                      <PublishButton key={a.target} poi={p} target={a.target}
                        label={a.label} kind={a.kind} onDone={() => void list.refetch()} />
                    ))}
                  </div>
                </td>
              </tr>
            ))}
          </Table>
          <div className="mt-4 flex items-center justify-end gap-2 text-sm">
            <Button kind="ghost" size="sm" disabled={page <= 1}
              onClick={() => setPage((n) => n - 1)}>上一页</Button>
            <span className="text-slate-500">{page} / {totalPages}</span>
            <Button kind="ghost" size="sm" disabled={page >= totalPages}
              onClick={() => setPage((n) => n + 1)}>下一页</Button>
          </div>
        </>
      )}
      {editing && (
        <EditModal
          poi={editing} floors={floors.data?.items ?? []}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); void list.refetch(); }}
        />
      )}
    </div>
  );
}

function PublishButton({ poi, target, label, kind, onDone }: {
  poi: Poi; target: PoiTarget; label: string;
  kind: "primary" | "ghost" | "danger"; onDone: () => void;
}) {
  const toast = useToast();
  const mutation = useMutation({
    mutationFn: () =>
      api(`/api/v1/pois/${poi.id}/publish`, {
        method: "POST", body: JSON.stringify({ target }),
      }),
    onSuccess: () => { toast("ok", `${poi.name} → ${label} 成功`); onDone(); },
    onError: (e) => toast("err", e instanceof ApiError ? e.message : "操作失败"),
  });
  return (
    <Button size="sm" kind={kind} disabled={mutation.isPending}
      onClick={() => mutation.mutate()}>
      {mutation.isPending ? "…" : label}
    </Button>
  );
}

function EditModal({ poi, floors, onClose, onSaved }: {
  poi: Poi; floors: Floor[]; onClose: () => void; onSaved: () => void;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    name: poi.name, intro: poi.intro ?? "",
    position_x: poi.position_x, position_y: poi.position_y,
    tags: (poi.tags ?? []).join("、"),
  });
  const [errors, setErrors] = useState<FieldError[]>([]);
  const [picking, setPicking] = useState(false);
  const floorName = floors.find((f) => f.id === poi.floor_id)?.name ?? "F1";

  const save = useMutation({
    mutationFn: () => {
      const tags = form.tags.split(/[、,，]/).map((t) => t.trim()).filter(Boolean);
      return api(`/api/v1/pois/${poi.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: form.name, intro: form.intro || null,
          position_x: Number(form.position_x), position_y: Number(form.position_y),
          tags,
        }),
      });
    },
    onSuccess: () => {
      toast("ok", "保存成功");
      void queryClient.invalidateQueries({ queryKey: ["pois"] });
      onSaved();
    },
    onError: (e) => toast("err", e instanceof ApiError ? e.message : "保存失败"),
  });

  function submit() {
    const errs = validatePoiForm({
      name: form.name,
      position_x: Number(form.position_x), position_y: Number(form.position_y),
      business_hours: {},
    });
    setErrors(errs);
    if (errs.length === 0) save.mutate();
  }

  const markers: MapMarker[] = [{ name: poi.name, floor: floorName,
    x: Number(form.position_x), y: Number(form.position_y) }];

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40"
      onClick={onClose}>
      <div className="max-h-[85vh] w-[520px] overflow-auto rounded-xl bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-base font-semibold text-slate-800">
            编辑 POI #{poi.id}（{floorName} 层）
          </h3>
          <Button kind="subtle" size="sm" onClick={onClose}>✕</Button>
        </div>
        <label className="mb-1 block text-xs text-slate-500">名称</label>
        <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        {errors.find((e) => e.field === "name") &&
          <p className="mt-1 text-xs text-red-600">{errors.find((e) => e.field === "name")!.message}</p>}
        <label className="mb-1 mt-3 block text-xs text-slate-500">简介</label>
        <Input value={form.intro} onChange={(e) => setForm({ ...form, intro: e.target.value })} />
        <label className="mb-1 mt-3 block text-xs text-slate-500">
          标签（顿号分隔）</label>
        <Input value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} />
        <label className="mb-1 mt-3 block text-xs text-slate-500">坐标（点击底图拾取）</label>
        <div className="flex items-center gap-2">
          <Input value={form.position_x} className="!w-24"
            onChange={(e) => setForm({ ...form, position_x: Number(e.target.value) })} />
          <Input value={form.position_y} className="!w-24"
            onChange={(e) => setForm({ ...form, position_y: Number(e.target.value) })} />
          <Button kind="ghost" size="sm" onClick={() => setPicking(!picking)}>
            {picking ? "收起底图" : "在底图上拾取"}
          </Button>
        </div>
        {errors.find((e) => e.field.startsWith("position")) &&
          <p className="mt-1 text-xs text-red-600">坐标必须为数字</p>}
        {picking && (
          <div className="mt-3 rounded-lg border border-slate-200 p-2">
            <FloorPlan
              floor={floorName} points={markers}
              draft={{ x: Number(form.position_x), y: Number(form.position_y) }}
              onPick={(x, y) => setForm((f) => ({ ...f, position_x: x, position_y: y }))}
            />
            <p className="mt-1 text-xs text-slate-400">点击平面图任意位置更新坐标（自动取整）</p>
          </div>
        )}
        <div className="mt-5 flex justify-end gap-2">
          <Button kind="ghost" onClick={onClose}>取消</Button>
          <Button onClick={submit} disabled={save.isPending}>
            {save.isPending ? "保存中…" : "保存"}
          </Button>
        </div>
      </div>
    </div>
  );
}
