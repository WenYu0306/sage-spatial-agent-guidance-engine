"""Agent 评测入口（CLAUDE.md 常用命令）。

--stage retrieval：对 eval_baseline.yaml 的 20 问跑知识检索，输出 Top3 命中率。
命中定义：Top3 片段（标题+正文）包含任一期望关键词；元语义键（出处/路线/列表）
不参与匹配（它们是回答阶段的要求，属 M5 评测）。
无 LLM_API_KEY 时自动落 MockProvider——向量语义随机，数字仅证明管线贯通，
须标注"待真实模型"。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg
import yaml
from knowledge_rag.provider import ProviderConfig
from knowledge_rag.retrieval import retrieve

REPO = Path(__file__).resolve().parents[1]
META_KEYS = {"出处", "路线", "列表"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="retrieval", choices=["retrieval"])
    ap.add_argument("--threshold", type=float, default=None)
    args = ap.parse_args()

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


if __name__ == "__main__":
    sys.exit(main())
