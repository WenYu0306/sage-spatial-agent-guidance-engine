"""Agent 评测入口（CLAUDE.md 常用命令）。

--stage retrieval：对 eval_baseline.yaml 的 20 问跑知识检索，输出 Top3 命中率。
命中定义：Top3 片段（标题+正文）包含任一期望关键词；元语义键（出处/路线/列表）
不参与匹配（它们是回答阶段的要求，属 M5 评测）。
无 LLM_API_KEY 时自动落 MockProvider——向量语义随机，数字仅证明管线贯通，
须标注"待真实模型"。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import psycopg
import yaml
from knowledge_rag.retrieval import retrieve
from platform_core.llm import ProviderConfig

REPO = Path(__file__).resolve().parents[1]
META_KEYS = {"出处", "路线", "列表"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="retrieval", choices=["retrieval", "full"])
    ap.add_argument("--threshold", type=float, default=None)
    ap.add_argument("--orch", default=os.environ.get("SVC_ORCHESTRATOR", "http://localhost:8941"))
    args = ap.parse_args()
    if args.stage == "full":
        return run_full(args)

    # .env 兜底加载
    env = REPO / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    baseline = yaml.safe_load((REPO / "deploy/seed/data/eval_baseline.yaml").read_text())
    provider_cfg = ProviderConfig.from_env()
    provider_kind = "real" if provider_cfg.api_key else "mock(待真实模型)"

    with psycopg.connect(
        os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
    ) as conn, conn.cursor() as cur:
        cur.execute("select id from tenants where code='shanqueli-demo'")
        tid = cur.fetchone()[0]
        cur.execute(
            "select v.id from venues v join tenants t on t.id=v.tenant_id "
            "where t.code='shanqueli-demo'"
        )
        vid = cur.fetchone()[0]

    hits = 0
    total = len(baseline["cases"])
    print(f"{'id':<4}{'问句':<16}{'命中':<4}  Top3 片段标题")
    print("-" * 76)
    for case in baseline["cases"]:
        q = case["question"]
        keys = [k for k in case.get("answer_keys", []) if k not in META_KEYS]
        results = retrieve(tid, vid, q, threshold=args.threshold)[:3]
        blob = " ".join(f"{r.title}{r.content}" for r in results)
        hit = any(str(k) in blob for k in keys)
        hits += hit
        titles = " | ".join(r.title for r in results) or "（空）"
        print(f"{case['id']:<4}{q:<16}{'✓' if hit else '✗':<4}  {titles[:44]}")
    print("-" * 76)
    print(f"Top3 命中率：{hits}/{total} = {hits / total:.0%}（provider={provider_kind}, "
          f"threshold={args.threshold if args.threshold is not None else 'env 默认'}）")
    return 0


def run_full(args) -> int:
    # 全链路评测：经 orchestrator SSE 真跑 20 问，输出 PRD 附录 B 口径的表
    import httpx

    orch = args.orch
    baseline = yaml.safe_load((REPO / "deploy/seed/data/eval_baseline.yaml").read_text())
    venue_id = int(os.environ.get("EVAL_VENUE_ID", "1"))

    def chat(message):
        events, cur_event, cur_data = [], "", ""
        with httpx.stream("POST", orch + "/api/v1/agent/chat",
                          json={"venue_id": venue_id, "message": message},
                          timeout=60) as resp:
            for line in resp.iter_lines():
                if line.startswith("event: "):
                    cur_event = line[7:]
                elif line.startswith("data: "):
                    cur_data = json.loads(line[6:])
                elif line == "" and cur_event:
                    events.append((cur_event, cur_data))
                    cur_event, cur_data = "", ""
        return events

    rows = []
    for case in baseline["cases"]:
        try:
            events = chat(case["question"])
        except Exception as exc:
            rows.append({"case": case, "actual": "EXC", "chain": [], "err": str(exc)[:50]})
            continue
        by_type = {}
        for ev, data in events:
            by_type.setdefault(ev, []).append(data)
        done = by_type.get("done", [{}])[-1]
        answer = "".join(d.get("text", "") for d in by_type.get("delta", []))
        cards = by_type.get("card", [])
        session_id = by_type.get("meta", [{}])[0].get("session_id")
        steps = httpx.get(orch + "/api/v1/agent/sessions/" + str(session_id) + "/trace",
                          timeout=30).json().get("steps", [])
        actual = "?"
        for st in steps:
            if st["step_type"] == "intent_parse" and st.get("output"):
                actual = st["output"].get("intent", "?")
                break
        chain = [st["tool_code"] for st in steps if st["step_type"] == "tool_call"]
        hallucinated = any(st["step_type"] == "post_validate" for st in steps)
        keys = [str(k) for k in case.get("answer_keys", []) if k not in META_KEYS]
        blob = answer + json.dumps(cards, ensure_ascii=False)
        poi_hit = any(k in blob for k in keys)
        type_check = {
            "venue_info": bool(by_type.get("citations")),
            "fallback": (not hallucinated) and done.get("status") == "ok",
            "coupon_claim": "coupon.claim" in chain or poi_hit,
        }.get(case["intent"], poi_hit or bool(chain))
        passed = (actual == case["intent"]) and type_check and done.get("status") == "ok"
        rows.append({"case": case, "actual": actual, "chain": chain,
                     "answer": answer[:26], "passed": passed,
                     "latency": done.get("latency_ms", 0), "hall": hallucinated})

    n_pass = sum(1 for r in rows if r.get("passed"))
    cols = ("id", "期望意图", "实际意图", "工具链", "幻觉", "ms", "结论")
    widths = (4, 14, 14, 22, 6, 6)
    print("  ".join(c.ljust(w) for c, w in zip(cols, widths)))
    print("-" * 100)
    for r in rows:
        if "err" in r:
            print("%-4s%-18s%-18s%-34s%-4s%-7s%s" % (r["case"]["id"], r["case"]["intent"],
                  r["actual"], "-", "-", "-", "EXC " + r["err"]))
        else:
            print("%-4s%-18s%-18s%-34s%-4s%-7s%s" % (
                r["case"]["id"], r["case"]["intent"], r["actual"],
                "->".join(r["chain"])[:32], "是" if r["hall"] else "否",
                r["latency"], chr(0x2713) if r["passed"] else chr(0x2717)))
    print("-" * 100)
    rate = 100.0 * n_pass / len(rows)
    print("全链路通过率：%d/%d = %.0f%%（orch=%s）" % (n_pass, len(rows), rate, orch))
    return 0


if __name__ == "__main__":

    sys.exit(main())
