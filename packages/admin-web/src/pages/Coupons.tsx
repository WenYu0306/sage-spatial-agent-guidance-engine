/** 优惠管理：列表 + 余量语气徽标（领取走 guest 侧，不在后台）。 */
import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api.ts";
import { remainingTone } from "../lib/actActions.ts";
import { Badge, Empty, LoadError, Spinner, Table } from "../components/ui.tsx";

type Coupon = {
  id: number; title: string; coupon_type: string; threshold: number;
  value: number; remaining: number; poi_id: number | null;
  start_at: string; end_at: string;
};
const TYPE_ZH: Record<string, string> = {
  discount: "折扣", full_reduction: "满减", gift: "赠品",
};

export default function CouponsPage() {
  const list = useQuery({
    queryKey: ["coupons"],
    queryFn: () => api<{ items: Coupon[] }>("/api/v1/coupons"),
    retry: 1,
  });
  if (list.isPending) return <Spinner />;
  if (list.isError) return <LoadError error={list.error} onRetry={() => void list.refetch()} />;
  if (list.data.items.length === 0) return <Empty text="暂无优惠券" />;
  return (
    <Table head={["标题", "类型", "门槛", "面值", "余量", "时间窗"]}>
      {list.data.items.map((c) => (
        <tr key={c.id} className="border-b border-slate-100">
          <td className="px-3 py-2 font-medium text-slate-700">{c.title}</td>
          <td className="px-3 py-2 text-slate-500">{TYPE_ZH[c.coupon_type] ?? c.coupon_type}</td>
          <td className="px-3 py-2 text-slate-500">满 {c.threshold}</td>
          <td className="px-3 py-2 text-slate-500">减 {c.value}</td>
          <td className="px-3 py-2"><Badge tone={remainingTone(c.remaining)}>{c.remaining} 张</Badge></td>
          <td className="px-3 py-2 text-xs text-slate-400">
            {c.start_at.slice(5, 10)} ~ {c.end_at.slice(5, 10)}
          </td>
        </tr>
      ))}
    </Table>
  );
}
