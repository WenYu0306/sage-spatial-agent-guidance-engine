/** trace 时间线视图（作品集演示）：输入 session_id → 拉取步骤序列 → 时间线渲染。 */

import { useMemo, useState } from "react";

interface TraceStep {
  id: number;
  message_id: number;
  trace_id: string;
  step_index: number;
  step_type: string;
  tool_code: string | null;
  input: Record<string, unknown> | null;
  output: Record<string, unknown> | null;
  status: string;
  latency_ms: number;
  error_code: number | null;
}

const TYPE_COLOR: Record<string, string> = {
  intent_parse: "#2563eb",
  tool_call: "#0f172a",
  rag: "#9333ea",
  post_validate: "#d97706",
  generate: "#16a34a",
};

export function TraceApp() {
  const [sessionId, setSessionId] = useState("");
  const [steps, setSteps] = useState<TraceStep[] | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const grouped = useMemo(() => {
    const map = new Map<number, TraceStep[]>();
    (steps ?? []).forEach((s) => {
      const arr = map.get(s.message_id) ?? [];
      arr.push(s);
      map.set(s.message_id, arr);
    });
    return [...map.entries()];
  }, [steps]);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const base = import.meta.env.VITE_ORCH_URL ?? "http://localhost:8941";
      const resp = await fetch(`${base}/api/v1/agent/sessions/${sessionId}/trace`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setSteps((await resp.json()).steps);
    } catch (e) {
      setError(String(e));
      setSteps(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ fontFamily: "system-ui, sans-serif", padding: 16, maxWidth: 960, margin: "0 auto" }}>
      <h1 style={{ fontSize: 22 }}>Agent Trace 时间线（作品集演示）</h1>
      <div style={{ display: "flex", gap: 8, margin: "12px 0" }}>
        <input value={sessionId} onChange={(e) => setSessionId(e.target.value)}
          placeholder="输入 session_id（如 36）" style={input} />
        <button onClick={load} disabled={!sessionId || loading} style={btn("#2563eb")}>
          {loading ? "加载中…" : "加载 trace"}
        </button>
      </div>
      {error && <p style={{ color: "#dc2626" }}>加载失败：{error}（orchestrator 在 8941 起了吗？）</p>}
      {steps && steps.length === 0 && <p style={{ color: "#64748b" }}>该会话暂无 trace</p>}
      {grouped.map(([mid, group]) => (
        <fieldset key={mid} style={{ border: "1px solid #e2e8f0", borderRadius: 8, marginBottom: 12 }}>
          <legend>message #{mid}</legend>
          {group.map((s) => (
            <div key={s.id} style={{ display: "flex", gap: 10, padding: "6px 0", borderBottom: "1px dashed #f1f5f9" }}>
              <span style={{ color: TYPE_COLOR[s.step_type] ?? "#64748b", fontWeight: 600, minWidth: 96 }}>
                {s.step_type}
              </span>
              <span style={{ color: "#64748b", minWidth: 110 }}>{s.tool_code ?? ""}</span>
              <span style={{
                color: s.status === "ok" ? "#16a34a" : s.status === "degraded" ? "#d97706" : "#dc2626",
                minWidth: 72,
              }}>{s.status}</span>
              <span style={{ color: "#64748b", minWidth: 70 }}>{s.latency_ms}ms</span>
              <span style={{ fontSize: 12, color: "#334155", flex: 1, overflow: "hidden" }}>
                {JSON.stringify(s.output)?.slice(0, 90)}
              </span>
            </div>
          ))}
        </fieldset>
      ))}
    </div>
  );
}

const btn = (bg: string): React.CSSProperties =>
  ({ background: bg, color: "white", border: "none", borderRadius: 6, padding: "8px 16px", cursor: "pointer" });
const input: React.CSSProperties =
  ({ flex: 1, padding: "6px 10px", border: "1px solid #cbd5e1", borderRadius: 6 });
