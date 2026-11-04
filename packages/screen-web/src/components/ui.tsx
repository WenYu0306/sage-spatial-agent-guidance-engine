/** 大屏自绘基础件（D-023 复制式，无运行时 UI 框架依赖）。 */

export function Spinner({ label = "加载中" }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 text-slate-300">
      <span className="inline-block size-8 animate-spin rounded-full border-4 border-sky-500/30 border-t-sky-400" />
      <span className="text-xl">{label}</span>
    </div>
  );
}

export function LoadError({ detail, onRetry }: { detail: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center gap-4 text-slate-300">
      <div className="text-3xl">出错了</div>
      <div className="text-xl text-slate-400">{detail}</div>
      {onRetry && (
        <button onClick={onRetry}
          className="rounded-xl bg-sky-600 px-8 py-3 text-2xl hover:bg-sky-500">
          重试
        </button>
      )}
    </div>
  );
}

export function Empty({ text }: { text: string }) {
  return <div className="text-xl text-slate-500">{text}</div>;
}

export function KioskShell({ children }: { children: React.ReactNode }) {
  return <div className="flex h-full flex-col p-10">{children}</div>;
}
