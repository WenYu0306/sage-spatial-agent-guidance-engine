/** shadcn 风格复制式组件（D-023：手写无运行时依赖）+ 五态基件（PRD 9）。 */
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

export function Spinner({ label = "加载中…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 p-8 text-sm text-slate-500" role="status">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-slate-600" />
      {label}
    </div>
  );
}

export function LoadError({ error, onRetry }: { error: Error; onRetry: () => void }) {
  return (
    <div className="m-4 rounded-lg border border-red-200 bg-red-50 p-6 text-sm">
      <p className="font-medium text-red-700">加载失败：{error.message}</p>
      <button onClick={onRetry} className="mt-3 rounded-md bg-red-600 px-3 py-1.5 text-white hover:bg-red-700">
        重试
      </button>
    </div>
  );
}

export function Empty({ text = "暂无数据" }: { text?: string }) {
  return <div className="p-10 text-center text-sm text-slate-400">{text}</div>;
}

export function Forbidden({ message = "你没有该操作的权限" }: { message?: string }) {
  return (
    <div className="m-4 rounded-lg border border-amber-200 bg-amber-50 p-6 text-sm text-amber-700">
      {message}（403/1003）
    </div>
  );
}

type Toast = { id: number; kind: "ok" | "err"; text: string };
const ToastCtx = createContext<(kind: "ok" | "err", text: string) => void>(() => undefined);

export function useToast() {
  return useContext(ToastCtx);
}

export function ToastHost({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((kind: "ok" | "err", text: string) => {
    const id = Date.now() + Math.random();
    setToasts((prev) => [...prev, { id, kind, text }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 3500);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed right-4 top-4 z-50 space-y-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`rounded-md px-4 py-2 text-sm text-white shadow-lg ${
              t.kind === "ok" ? "bg-emerald-600" : "bg-red-600"
            }`}
          >
            {t.text}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export function Button({
  children, onClick, kind = "primary", disabled, type = "button", size = "md", className = "",
}: {
  children: ReactNode;
  onClick?: () => void;
  kind?: "primary" | "ghost" | "danger" | "subtle";
  disabled?: boolean;
  type?: "button" | "submit";
  size?: "sm" | "md";
  className?: string;
}) {
  const kinds = {
    primary: "bg-slate-800 text-white hover:bg-slate-700",
    ghost: "border border-slate-300 bg-white text-slate-700 hover:bg-slate-50",
    danger: "bg-red-600 text-white hover:bg-red-700",
    subtle: "text-slate-600 hover:bg-slate-100",
  } as const;
  return (
    <button
      type={type}
      disabled={disabled}
      onClick={onClick}
      className={`rounded-md font-medium disabled:cursor-not-allowed disabled:opacity-50 ${
        size === "sm" ? "px-2.5 py-1 text-xs" : "px-3.5 py-1.5 text-sm"
      } ${kinds[kind]} ${className}`}
    >
      {children}
    </button>
  );
}

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  const { className = "", ...rest } = props;
  return (
    <input
      {...rest}
      className={`w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm outline-none focus:border-slate-500 ${className}`}
    />
  );
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  const { className = "", ...rest } = props;
  return (
    <select
      {...rest}
      className={`rounded-md border border-slate-300 px-2 py-1.5 text-sm ${className}`}
    />
  );
}

export function Badge({ children, tone = "slate" }: { children: ReactNode; tone?: string }) {
  const tones: Record<string, string> = {
    slate: "bg-slate-100 text-slate-600",
    green: "bg-emerald-100 text-emerald-700",
    amber: "bg-amber-100 text-amber-700",
    red: "bg-red-100 text-red-700",
    blue: "bg-blue-100 text-blue-700",
  };
  return (
    <span className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${tones[tone] ?? tones.slate}`}>
      {children}
    </span>
  );
}

export function Table({ head, children }: { head: string[]; children: ReactNode }) {
  return (
    <table className="w-full text-left text-sm">
      <thead>
        <tr className="border-b border-slate-200 text-xs uppercase text-slate-400">
          {head.map((h) => (
            <th key={h} className="px-3 py-2 font-medium">
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>{children}</tbody>
    </table>
  );
}
