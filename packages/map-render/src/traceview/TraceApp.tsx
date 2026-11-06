/** trace 时间线视图（作品集演示）：输入 session_id → 拉取步骤序列 → furrow 风格时间线。
    U1-f：步骤 chip / 时延条形 / 状态徽标 / JSON 折叠（原为裸 JSON 表格）。 */

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

const C = {
  paper: "#f7f4ed",
  paper2: "#fdfcf8",
  paper3: "#eeeade",
  ink: "#2b2925",
  ink2: "#44403c",
  muted: "#78716c",
  rule: "#e7e2d8",
  accentDeep: "#c2410c",
  ok: "#15803d",
  warn: "#d97706",
  danger: "#dc2626",
};

const TYPE_COLOR: Record<string, string> = {
  intent_parse: "#1d4ed8",
  tool_call: C.ink2,
  rag: "#9333ea",
  post_validate: C.warn,
  generate: C.ok,
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
      const base = import.meta.env.VITE_ORCH_URL ?? "";
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
    <div style={{ minHeight: "100vh", background: C.paper, color: C.ink,
                  fontFamily: '"Red Hat Text", "PingFang SC", "Hiragino Sans GB", sans-serif', padding: 24 }}>
      <div style={{ maxWidth: 960, margin: "0 auto" }}>
        <h1 style={{ fontSize: 22, fontWeight: 600, letterSpacing: "-0.02em" }}>
          Agent Trace 时间线
          <span style={{ fontSize: 13, fontWeight: 400, color: C.muted, marginLeft: 10 }}>作品集演示 · 每步可回放</span>
        </h1>
        <div style={{ display: "flex", gap: 8, margin: "14px 0 18px" }}>
          <input value={sessionId} onChange={(e) => setSessionId(e.target.value)}
            placeholder="输入 session_id（如 36）" style={inputStyle} />
          <button onClick={load} disabled={!sessionId || loading} style={btnStyle}>
            {loading ? "加载中…" : "加载 trace"}
          </button>
        </div>
        {error && (
          <p style={{ color: C.danger, border: `1px solid ${C.danger}33`, background: `${C.danger}0d`,
                      borderRadius: 8, padding: "8px 12px", fontSize: 13 }}>
            加载失败：{error}（orchestrator 在 8941 起了吗？）
          </p>
        )}
        {steps && steps.length === 0 && <p style={{ color: C.muted }}>该会话暂无 trace</p>}
        {grouped.map(([mid, group]) => {
          const maxLat = Math.max(...group.map((s) => s.latency_ms), 1);
          return (
            <div key={mid} style={{ background: C.paper2, border: `1px solid ${C.rule}`, borderRadius: 10,
                                     boxShadow: "0 10px 24px -14px rgba(43,41,37,.2)", marginBottom: 14,
                                     padding: "14px 16px" }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: C.muted, marginBottom: 8 }}>
                message #{mid}
              </div>
              {group.map((s) => (
                <div key={s.id} style={{ display: "grid",
                                          gridTemplateColumns: "130px 110px 74px 1fr",
                                          gap: 12, alignItems: "center",
                                          padding: "7px 0", borderBottom: `1px dashed ${C.rule}` }}>
                  <span style={{ fontSize: 13, fontWeight: 600, color: TYPE_COLOR[s.step_type] ?? C.muted }}>
                    {s.step_type}
                  </span>
                  <span style={{ fontSize: 13, color: C.ink2 }}>{s.tool_code ?? ""}</span>
                  <span style={{
                    fontSize: 12, textAlign: "center", borderRadius: 6, padding: "1px 0",
                    border: `1px solid ${s.status === "ok" ? C.ok : s.status === "degraded" ? C.warn : C.danger}55`,
                    color: s.status === "ok" ? C.ok : s.status === "degraded" ? C.warn : C.danger,
                    background: s.status === "ok" ? `${C.ok}0d` : s.status === "degraded" ? `${C.warn}0d` : `${C.danger}0d`,
                  }}>
                    {s.status}{s.error_code != null ? ` · ${s.error_code}` : ""}
                  </span>
                  <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ flex: 1, height: 6, background: C.paper3, borderRadius: 3, overflow: "hidden" }}>
                      <span style={{ display: "block", height: "100%",
                                     width: `${Math.max(2, (s.latency_ms / maxLat) * 100)}%`,
                                     background: TYPE_COLOR[s.step_type] ?? C.muted, borderRadius: 3 }} />
                    </span>
                    <span style={{ fontSize: 12, color: C.muted, minWidth: 52, textAlign: "right" }}>
                      {s.latency_ms}ms
                    </span>
                    <details style={{ minWidth: 0 }}>
                      <summary style={{ fontSize: 12, color: C.accentDeep, cursor: "pointer" }}>数据</summary>
                      <pre style={{ fontSize: 11, background: C.paper3, borderRadius: 6, padding: 8,
                                    whiteSpace: "pre-wrap", wordBreak: "break-all", maxHeight: 260,
                                    overflow: "auto", margin: "6px 0 0" }}>
{`IN  ${JSON.stringify(s.input)}\nOUT ${JSON.stringify(s.output)}`}
                      </pre>
                    </details>
                  </span>
                </div>
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}

const btnStyle: React.CSSProperties = {
  background: C.accentDeep, color: "#fff", border: "none", borderRadius: 6,
  padding: "8px 16px", cursor: "pointer", fontWeight: 500,
};
const inputStyle: React.CSSProperties = {
  flex: 1, padding: "8px 10px", border: `1px solid ${C.rule}`, borderRadius: 6,
  background: C.paper2, color: C.ink,
};
