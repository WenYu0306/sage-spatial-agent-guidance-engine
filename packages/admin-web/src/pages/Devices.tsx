/** 设备列表（platform_admin/venue_admin）：GET /api/v1/devices。 */
import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api.ts";
import { Badge, Empty, LoadError, Spinner, Table } from "../components/ui.tsx";

type Device = {
  id: number; code: string; name: string; device_type: string;
  status: string; last_seen_at: string | null; app_version: string | null;
  floor: string | null;
};
const STATUS_ZH: Record<string, { label: string; tone: string }> = {
  online: { label: "在线", tone: "green" },
  offline: { label: "离线", tone: "slate" },
  maintenance: { label: "维护中", tone: "amber" },
};

export default function DevicesPage() {
  const list = useQuery({
    queryKey: ["devices"],
    queryFn: () => api<{ items: Device[] }>("/api/v1/devices"),
    retry: 1,
  });
  if (list.isPending) return <Spinner />;
  if (list.isError) return <LoadError error={list.error} onRetry={() => void list.refetch()} />;
  if (list.data.items.length === 0) return <Empty text="暂无设备（大屏接入后出现在此）" />;
  return (
    <Table head={["设备", "编码", "类型", "楼层", "状态", "最近心跳", "版本"]}>
      {list.data.items.map((d) => (
        <tr key={d.id} className="border-b border-slate-100">
          <td className="px-3 py-2 font-medium text-slate-700">{d.name}</td>
          <td className="px-3 py-2 text-xs text-slate-400">{d.code}</td>
          <td className="px-3 py-2 text-slate-500">{d.device_type}</td>
          <td className="px-3 py-2 text-slate-500">{d.floor ?? "-"}</td>
          <td className="px-3 py-2">
            <Badge tone={STATUS_ZH[d.status]?.tone ?? "slate"}>
              {STATUS_ZH[d.status]?.label ?? d.status}
            </Badge>
          </td>
          <td className="px-3 py-2 text-xs text-slate-400">
            {d.last_seen_at ? d.last_seen_at.slice(0, 16).replace("T", " ") : "从未"}
          </td>
          <td className="px-3 py-2 text-xs text-slate-400">{d.app_version ?? "-"}</td>
        </tr>
      ))}
    </Table>
  );
}
