/** 大屏问答页：③ 提交实现 SSE 全链路；当前为导航占位。 */

import { KioskShell } from "../components/ui.tsx";
import type { DeviceIdentity } from "../lib/device.ts";

export function Chat({
  session: _session,
  seed: _seed,
  onBack,
}: {
  session: DeviceIdentity;
  seed: string;
  onBack: () => void;
}) {
  return (
    <KioskShell>
      <button onClick={onBack}
        className="self-start rounded-lg bg-slate-800 px-6 py-2 text-xl">
        ← 返回首页
      </button>
      <div className="flex flex-1 items-center justify-center text-2xl text-slate-500">
        问答页（③ 提交实现 SSE 流式问答）
      </div>
    </KioskShell>
  );
}
