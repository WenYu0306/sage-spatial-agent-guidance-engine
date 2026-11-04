/** 问答页：guest 匿名 SSE（复用共享解析器；不带 device_id——PRD 7.1 仅大屏必填）。 */

import { useRef, useState } from "react";
import { createSSEParser } from "@sage/map-render/src/lib/http/sse.ts";
import { TopBar } from "../components/ui.tsx";
import { anonymousId } from "../lib/guest.ts";

interface ChatMessage {
  role: "user" | "ai";
  text: string;
  degraded?: boolean;
}

const VENUE_ID = 1;

export function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);

  async function send(raw: string) {
    const text = raw.trim();
    if (!text || busy) return;
    setDraft("");
    setMessages((m) => [...m, { role: "user", text }, { role: "ai", text: "" }]);
    setBusy(true);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      const resp = await fetch("/api/v1/agent/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Client": "mobile" },
        body: JSON.stringify({
          venue_id: VENUE_ID, message: text,
          anonymous_id: anonymousId(),
        }),
        signal: ctrl.signal,
      });
      if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`);
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      const parser = createSSEParser((event, data) => {
        const payload = JSON.parse(data);
        if (event === "delta") {
          setMessages((m) => {
            const last = m[m.length - 1];
            if (last?.role === "ai") {
              return [...m.slice(0, -1), { ...last, text: last.text + payload.text }];
            }
            return m;
          });
        } else if (event === "done" && payload.status !== "ok") {
          setMessages((m) => {
            const last = m[m.length - 1];
            if (last?.role === "ai") return [...m.slice(0, -1), { ...last, degraded: true }];
            return m;
          });
        }
      });
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        parser(decoder.decode(value, { stream: true }));
      }
    } catch {
      setMessages((m) => {
        const last = m[m.length - 1];
        if (last?.role === "ai" && !last.text) {
          return [...m.slice(0, -1), { ...last, text: "网络开小差了，请稍后再试" }];
        }
        return m;
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full flex-col">
      <TopBar title="问一问" />
      <div ref={listRef} className="flex-1 space-y-3 overflow-y-auto p-3">
        {messages.length === 0 && (
          <div className="pt-10 text-center text-sm text-slate-400">
            问问商场的事，比如「最近的服务台在哪」
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
            <div className={`max-w-[85%] rounded-2xl px-4 py-2 text-sm ${
              m.role === "user" ? "bg-sky-600 text-white" : "bg-white shadow-sm"}`}>
              <div className="whitespace-pre-wrap">{m.text || "…"}</div>
              {m.degraded && <div className="mt-1 text-xs text-amber-600">部分能力降级</div>}
            </div>
          </div>
        ))}
      </div>
      <form className="flex gap-2 border-t border-slate-200 bg-white p-3"
        onSubmit={(e) => { e.preventDefault(); void send(draft); }}>
        <input value={draft} onChange={(e) => setDraft(e.target.value)}
          placeholder="输入问题…"
          className="flex-1 rounded-full bg-slate-100 px-4 py-2 text-sm outline-none
                     focus:ring-2 focus:ring-sky-400" />
        <button type="submit" disabled={busy || !draft.trim()}
          className="rounded-full bg-sky-600 px-5 py-2 text-sm text-white disabled:opacity-40">
          发送
        </button>
      </form>
    </div>
  );
}
