/** PoiPicker 点位标注工具：拾点 → 表单 → 列表 → 导出/导入 pois_*.yaml 行。 */

import { useMemo, useState } from "react";
import { parseYamlDoc, toYamlDoc } from "../lib/poiExport.ts";
import { upsertPoint } from "../lib/pointList.ts";
import type { PoiPoint } from "../lib/types.ts";
import { FloorPlan } from "./FloorPlan.tsx";
import { MapStage } from "./MapStage.tsx";

const FLOORS = ["B1", "F1", "F2"] as const;
const CATEGORIES = [
  "restaurant", "chinese", "hotpot", "japanese", "western", "coffee_tea", "bakery",
  "fastfood", "retail", "fashion", "shoes_bags", "digital", "beauty", "jewelry",
  "toys_books", "glasses", "supermarket", "cinema", "gym", "kids_play", "education",
  "salon", "life_service", "toilet", "nursing_room", "elevator", "escalator",
  "info_desk", "parking", "atm", "charging_station", "clinic",
];

const emptyForm = {
  name: "",
  category: "fashion",
  hours: "10:00-22:00",
  tags: "",
  hot: 60,
};

export function App() {
  const [floor, setFloor] = useState<string>("F1");
  const [points, setPoints] = useState<PoiPoint[]>([]);
  const [draft, setDraft] = useState<PoiPoint | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [importText, setImportText] = useState("");
  const [showExport, setShowExport] = useState(false);
  const [copied, setCopied] = useState(false);

  async function copyYaml() {
    try {
      await navigator.clipboard.writeText(yamlOut);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setShowExport(true); // 剪贴板不可用（非安全上下文等）→ 展开面板兜底
    }
  }

  const yamlOut = useMemo(
    () => toYamlDoc(points.filter((p) => p.floor === floor), floor),
    [points, floor],
  );

  function onPick(x: number, y: number) {
    const p: PoiPoint = {
      name: form.name || "未命名",
      category: form.category,
      floor,
      x,
      y,
      hours: form.hours,
      tags: form.tags.split(/[,，]/).map((t) => t.trim()).filter(Boolean),
      hot: form.hot,
    };
    setDraft(p);
  }

  function confirmDraft() {
    if (!draft) return;
    setPoints((prev) => upsertPoint(prev, draft));
    // 草稿坐标保留（录入笔语义）：改名/点击新位置后可连续录入，同名覆盖
    setForm((f) => ({ ...f, name: "" }));
  }

  function doImport() {
    const imported = parseYamlDoc(importText, floor);
    if (imported.length === 0) return;
    setPoints((prev) => [
      ...prev.filter((q) => !imported.some((p) => p.name === q.name)),
      ...imported,
    ]);
    setImportText("");
  }

  return (
    <div style={{ fontFamily: "system-ui, sans-serif", padding: 16, maxWidth: 1280, margin: "0 auto" }}>
      <h1 style={{ fontSize: 22, margin: "0 0 12px" }}>
        PoiPicker · 山雀里·栖云广场点位标注
        <span style={{ fontSize: 13, color: "#64748b", marginLeft: 12 }}>
          点击地图拾点 → 填表 → 加入列表 → 导出 YAML 贴回 seed
        </span>
      </h1>
      <div style={{ marginBottom: 10, display: "flex", gap: 8 }}>
        {FLOORS.map((f) => (
          <button key={f} onClick={() => setFloor(f)}
            style={btn(floor === f ? "#2563eb" : "#e2e8f0", floor === f ? "white" : "#0f172a")}>
            {f}
          </button>
        ))}
        <button onClick={copyYaml} style={btn(copied ? "#16a34a" : "#0f172a", "white")}>
          {copied ? "已复制 ✓" : `复制 YAML（${points.filter((p) => p.floor === floor).length} 点）`}
        </button>
        <button onClick={() => setShowExport((v) => !v)} style={btn("#e2e8f0", "#0f172a")}>
          {showExport ? "收起" : "查看"}
        </button>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 16 }}>
        <MapStage>
          <FloorPlan floor={floor} points={points} draft={draft} onPick={onPick} />
        </MapStage>
        <div>
          <fieldset style={panel}>
            <legend>新点表单（当前层 {floor}）</legend>
            <label>名称 <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} style={input} /></label>
            <label>分类 <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} style={input}>
              {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select></label>
            <label>营业时间 <input value={form.hours} onChange={(e) => setForm({ ...form, hours: e.target.value })} style={input} /></label>
            <label>标签（逗号分隔）<input value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} style={input} /></label>
            <label>热度 <input type="number" min={0} max={100} value={form.hot}
              onChange={(e) => setForm({ ...form, hot: Number(e.target.value) })} style={input} /></label>
            <button onClick={confirmDraft} disabled={!draft} style={btn(draft ? "#16a34a" : "#e2e8f0", draft ? "white" : "#94a3b8")}>
              {draft ? `加入列表（${draft.x}, ${draft.y}）` : "先在地图上点一个位置"}
            </button>
          </fieldset>
          <fieldset style={panel}>
            <legend>点位列表（{floor}，{points.filter((p) => p.floor === floor).length}）</legend>
            <ul style={{ listStyle: "none", margin: 0, padding: 0, maxHeight: 180, overflowY: "auto" }}>
              {points.filter((p) => p.floor === floor).map((p) => (
                <li key={p.name} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0" }}>
                  <span>{p.name} <small style={{ color: "#64748b" }}>({p.x},{p.y})</small></span>
                  <button onClick={() => setPoints((prev) => prev.filter((q) => q.name !== p.name))}>删</button>
                </li>
              ))}
            </ul>
          </fieldset>
          <fieldset style={panel}>
            <legend>导入已有 YAML 行（微调工作流）</legend>
            <textarea value={importText} onChange={(e) => setImportText(e.target.value)}
              rows={4} placeholder="粘贴 pois_f1.yaml 里的 - {name: ...} 行…" style={{ ...input, width: "100%" }} />
            <button onClick={doImport} style={btn("#2563eb", "white")}>导入到当前层</button>
          </fieldset>
        </div>
      </div>
      {showExport && (
        <textarea readOnly value={yamlOut} rows={12} style={{ ...input, width: "100%", marginTop: 12, fontFamily: "monospace" }} />
      )}
    </div>
  );
}

const btn = (bg: string, fg: string): React.CSSProperties => ({
  background: bg, color: fg, border: "none", borderRadius: 6,
  padding: "7px 14px", cursor: "pointer", fontSize: 14,
});
const panel: React.CSSProperties = { border: "1px solid #e2e8f0", borderRadius: 8, marginBottom: 10 };
const input: React.CSSProperties = { width: "100%", boxSizing: "border-box", margin: "3px 0 9px", padding: "5px 8px" };
