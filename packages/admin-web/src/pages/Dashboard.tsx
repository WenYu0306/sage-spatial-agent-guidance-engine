/** 数据看板：M9 analytics-service 未接入——规范空态（PRD 9 五态之"空数据"）。 */
export default function DashboardPage() {
  return (
    <div className="flex max-w-xl flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 bg-white p-16 text-center">
      <p className="text-base font-medium text-slate-600">数据看板尚未开通</p>
      <p className="mt-2 max-w-sm text-xs leading-5 text-slate-400">
        看板指标（AI 问答量/搜索量/导航到店/领券）依赖 M9 analytics-service 的埋点聚合，
        该模块在交付排期中尚未启动。埋点采集（F-15）与看板将随后续任务接入。
      </p>
      <p className="mt-4 text-xs text-slate-300">M9 · 未接入</p>
    </div>
  );
}
