/** 场地列表（platform_admin/venue_admin）：GET /api/v1/venues，五态齐全。 */
import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api.ts";
import { Badge, Empty, LoadError, Spinner, Table } from "../components/ui.tsx";

type Venue = { id: number; name: string; venue_type: string; status: string; tenant_id: number };

export default function VenuesPage() {
  const query = useQuery({
    queryKey: ["venues"],
    queryFn: () => api<{ items: Venue[] }>("/api/v1/venues"),
    retry: 1,
  });
  if (query.isPending) return <Spinner />;
  if (query.isError) return <LoadError error={query.error} onRetry={() => void query.refetch()} />;
  if (query.data.items.length === 0) return <Empty text="当前租户暂无场地" />;
  return (
    <div>
      <h2 className="mb-4 text-lg font-semibold text-slate-800">场地列表</h2>
      <Table head={["ID", "名称", "类型", "状态"]}>
        {query.data.items.map((v) => (
          <tr key={v.id} className="border-b border-slate-100">
            <td className="px-3 py-2 text-slate-500">{v.id}</td>
            <td className="px-3 py-2 font-medium text-slate-700">{v.name}</td>
            <td className="px-3 py-2 text-slate-500">{v.venue_type}</td>
            <td className="px-3 py-2">
              <Badge tone={v.status === "active" ? "green" : "amber"}>{v.status}</Badge>
            </td>
          </tr>
        ))}
      </Table>
    </div>
  );
}
