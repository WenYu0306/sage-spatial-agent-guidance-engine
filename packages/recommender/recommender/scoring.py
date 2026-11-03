"""M7 推荐打分内核（纯函数，零业务词，零 DB 依赖）。

score = Σ (factor_score_i × weight_i)（PRD 8.4）。候选特征由服务层装配：
泛化特征（距离/楼层差/营业状态/热度/权重/标签/主动线距离）服务内计算，
营销旗标（has_promotion）由调用方传入——营销数据表属业务层，不进内核。
休息中的候选直接过滤；候选为空返回空列表不报错（PRD 8.5）。
"""

from __future__ import annotations

from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "recommend_weights.yaml"

DEFAULT_WEIGHTS = {
    "distance": 0.22, "floor_diff": 0.10, "business": 0.15, "promotion": 0.15,
    "merchant": 0.10, "hot": 0.10, "tag_match": 0.13, "convenience": 0.05,
}
DEFAULT_SCALES = {"distance_m": 1000.0, "floor_diff": 5.0, "trunk_m": 300.0}

# 理由模板（人类可读、业务中性；PRD 8.5：最多 3 条）
REASON_LABELS = {
    "distance": "距离最近",
    "floor_diff": "同层或就近楼层",
    "business": "正在营业",
    "promotion": "有进行中的活动",
    "merchant": "商家主推",
    "hot": "热度较高",
    "tag_match": "符合你的偏好",
    "convenience": "就在主动线旁",
}


class LoadableWeights:
    """从 config/recommend_weights.yaml 读权重与归一化刻度（每次实例化读盘，改文件即生效）。"""

    def __init__(self, weights: dict, scales: dict):
        self.weights = dict(weights)
        self.scales = dict(scales)

    @classmethod
    def default(cls) -> "LoadableWeights":
        with CONFIG_PATH.open(encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        return cls(cfg["factors"], cfg.get("scales", DEFAULT_SCALES))

    def as_dict(self) -> dict:
        return dict(self.weights)


def _minmax(value: float, all_values: list[float]) -> float:
    lo, hi = min(all_values), max(all_values)
    if hi - lo < 1e-12:
        return 0.5
    return (value - lo) / (hi - lo)


def factor_scores(cand: dict, ctx: dict, all_candidates: list[dict] | None = None,
                  weights: LoadableWeights | None = None) -> dict:
    """单候选八因子得分（0..1）。all_candidates 供 min-max 归一化。"""
    scales = (weights or LoadableWeights.default()).scales
    pool = all_candidates or [cand]
    tags_ctx = ctx.get("tags") or []
    cand_tags = set(cand.get("tags") or [])
    tag_match = (len(cand_tags & set(tags_ctx)) / len(tags_ctx)
                 if tags_ctx else 0.5)
    status = cand.get("business_status", "open")
    return {
        "distance": 1 - min(cand.get("distance_m", 0.0) / scales["distance_m"], 1.0),
        "floor_diff": 1 - min(cand.get("floor_diff", 0) / scales["floor_diff"], 1.0),
        "business": {"open": 1.0, "closing_soon": 0.4, "closed": 0.0}.get(status, 0.0),
        "promotion": 1.0 if cand.get("has_promotion") else 0.0,
        "merchant": _minmax(float(cand.get("recommend_weight", 1.0)),
                            [float(c.get("recommend_weight", 1.0)) for c in pool]),
        "hot": _minmax(float(cand.get("hot_score", 0.0)),
                       [float(c.get("hot_score", 0.0)) for c in pool]),
        "tag_match": tag_match,
        "convenience": 1 - min(cand.get("trunk_dist_m", 0.0) / scales["trunk_m"], 1.0),
    }


def weighted_score(factors: dict, weights: dict) -> float:
    """纯数学不加舍入；输出层（API 响应/日志落库）自行保留位数。"""
    return sum(factors[k] * w for k, w in weights.items())


def score_candidates(candidates: list[dict], ctx: dict,
                     weights: LoadableWeights | None = None) -> list[dict]:
    """打分并降序排序；closed 过滤；空入参返回空列表。"""
    if not candidates:
        return []
    lw = weights or LoadableWeights.default()
    alive = [c for c in candidates if c.get("business_status") != "closed"]
    rows = []
    for c in alive:
        fs = factor_scores(c, ctx, all_candidates=alive, weights=lw)
        rows.append({"poi_id": c["poi_id"], "name": c.get("name", ""),
                     "score": weighted_score(fs, lw.weights), "factors": fs})
    rows.sort(key=lambda r: r["score"], reverse=True)
    for row in rows:
        row["reasons"] = _reasons(row["factors"], lw.weights)
    return rows


def _reasons(factors: dict, weights: dict) -> list[str]:
    """取贡献最大的 ≤3 个因子生成理由（分<0.5 的因子不值得提）。"""
    contrib = sorted(factors.items(), key=lambda kv: kv[1] * weights[kv[0]],
                     reverse=True)
    return [REASON_LABELS[k] for k, v in contrib if v >= 0.5][:3]
