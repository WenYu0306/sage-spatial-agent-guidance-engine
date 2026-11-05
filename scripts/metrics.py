#!/usr/bin/env python3
"""监控五指标消费端（13.6）：读 agent-orchestrator /api/v1/agent/stats 并打印人读摘要。

配套 /stats 端点（无鉴权内网端点，ASSUMPTIONS A6）；转生产时本脚本可原样接
告警系统的 JSON 探针。

用法：uv run python scripts/metrics.py [--hours 24] [--base http://127.0.0.1:8941]
"""

from __future__ import annotations

import argparse
import sys

import httpx


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--base", default="http://127.0.0.1:8941")
    args = ap.parse_args()

    try:
        d = httpx.get(f"{args.base}/api/v1/agent/stats",
                      params={"hours": args.hours}, timeout=10).json()
    except Exception as e:  # 服务不可达：运维脚本失败要可见，不吞异常
        print(f"✗ /stats 不可达（{args.base}）：{e}", file=sys.stderr)
        return 1

    pct = lambda x: f"{x * 100:.1f}%"  # noqa: E731
    print(f"窗口 {d['window_hours']}h · 消息 {d['messages']} 条")
    print(f"AI 调用成功率 {pct(d['ai_call_success_rate'])} | 降级率 "
          f"{pct(d['degraded_rate'])} | trace 完整率 {pct(d['trace_complete_rate'])}")
    lat = d["avg_latency_ms"]
    print("平均时延 ms：", " | ".join(f"{k} {v}" for k, v in sorted(lat.items())))
    print(f"token：入 {d['tokens']['in']} / 出 {d['tokens']['out']}")
    if d["error_codes"]:
        print("错误码：", " | ".join(f"{k}×{v}" for k, v in d["error_codes"].items()))
    else:
        print("错误码：无")
    return 0


if __name__ == "__main__":
    sys.exit(main())
