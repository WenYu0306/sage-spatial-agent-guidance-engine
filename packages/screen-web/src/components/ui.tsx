/** 大屏自绘基础件（D-023 复制式，无运行时 UI 框架依赖）。 */

export function Spinner({ label = "加载中" }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 text-ink-2">
      <span className="inline-block size-8 animate-spin rounded-full border-4 border-accent/30 border-t-accent-deep" />
      <span className="text-xl">{label}</span>
    </div>
  );
}

export function LoadError({ detail, onRetry }: { detail: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center gap-4 text-ink">
      <div className="text-3xl">出错了</div>
      <div className="text-xl text-muted">{detail}</div>
      {onRetry && (
        <button onClick={onRetry}
          className="rounded-xl bg-accent px-8 py-3 text-2xl text-ink hover:bg-accent-deep">
          重试
        </button>
      )}
    </div>
  );
}

export function Empty({ text }: { text: string }) {
  return <div className="text-xl text-muted">{text}</div>;
}

export function KioskShell({ children }: { children: React.ReactNode }) {
  // pb-28 给右下角无障碍浮动按钮让位，避免遮挡输入区
  return <div className="flex h-full flex-col p-10 pb-28">{children}</div>;
}
