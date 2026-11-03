"""单模块演示：真库候选 → 八因子打分 → factors/reasons 展示。

cd packages/recommender && make demo（前置：make migrate && make seed）
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg

from .app import _now
from .features import gather
from .scoring import LoadableWeights, score_candidates


def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parents[3] / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip("'").strip('"'))


def main() -> int:
    _load_dotenv()
    # 演示在任何真实时刻可跑：未显式配置时注入正午（营业时段内）
    os.environ.setdefault("SAGE_TIME_OVERRIDE", "2026-11-04T12:00:00")
    dsn = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("select id from tenants where code='shanqueli-demo'")
        tid = cur.fetchone()[0]
        cur.execute("select id, timezone from venues where tenant_id=%s limit 1", (tid,))
        vid, tz = cur.fetchone()
        cur.execute(
            "select id from floors where venue_id=%s and level=1", (vid,))
        f1 = cur.fetchone()[0]
        cur.execute(
            "select p.id from pois p join poi_categories c on "
            "c.tenant_id=p.tenant_id and c.code=p.category_code "
            "where p.venue_id=%s and c.is_facility=false "
            "and p.deleted_at is null order by p.id limit 5", (vid,))
        ids = [r[0] for r in cur.fetchall()]
        cands = gather(cur, tid, vid, ids,
                       {"x": 600.0, "y": 400.0, "floor_id": f1},
                       _now(tz).replace(tzinfo=None))
        closed_n = sum(1 for c in cands if c["business_status"] == "closed")
    for c in cands[:3]:
        c["has_promotion"] = c["poi_id"] == ids[0]  # 演示营销旗标由调用方注入
    ranked = score_candidates(cands, {"tags": ["约会"]},
                              weights=LoadableWeights.default())
    by_id = {c["poi_id"]: c for c in cands}
    for row in ranked:
        row["floor"] = by_id[row["poi_id"]].get("floor")
    print(f"候选 {len(cands)} 个（其中休息中 {closed_n} 个将被过滤，"
          f"时间注入 {os.environ['SAGE_TIME_OVERRIDE']}）")
    for i, row in enumerate(ranked, start=1):
        f = row["factors"]
        print(f"#{i} {row['name']}  score={row['score']:.4f}  floor={row.get('floor')}")
        print(f"   reasons={row['reasons']}")
        print(f"   factors={ {k: round(v, 3) for k, v in f.items()} }")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
