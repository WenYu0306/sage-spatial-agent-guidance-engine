/** 移动端基础件：骨架屏/错误/空态（PRD 825 降级四件套之呈现层）。 */

export function Skeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-3 p-4" data-testid="skeleton">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-16 animate-pulse rounded-xl bg-slate-200" />
      ))}
    </div>
  );
}

export function LoadError({ detail, onRetry }: { detail: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center gap-3 p-8 text-center">
      <div className="text-lg font-semibold">{detail}</div>
      {onRetry && (
        <button onClick={onRetry}
          className="rounded-full bg-sky-600 px-6 py-2 text-sm text-white">重试</button>
      )}
    </div>
  );
}

export function Empty({ text }: { text: string }) {
  return <div className="p-8 text-center text-sm text-slate-500">{text}</div>;
}

export function TopBar({ title, back }: { title: string; back?: () => void }) {
  return (
    <header className="flex items-center gap-3 border-b border-slate-200 bg-white px-4 py-3">
      {back && <button onClick={back} className="text-xl leading-none">←</button>}
      <h1 className="text-base font-semibold">{title}</h1>
    </header>
  );
}
