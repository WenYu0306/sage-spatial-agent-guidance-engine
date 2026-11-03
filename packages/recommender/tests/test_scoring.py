"""M7 打分内核单元测试（纯函数，PRD 8.4 八因子；覆盖率红线 ≥80%）。"""

from __future__ import annotations

import pytest
from recommender.scoring import (
    DEFAULT_WEIGHTS,
    LoadableWeights,
    factor_scores,
    score_candidates,
)

# ---------- 特征构造辅助 ----------

def cand(**kw):
    base = dict(poi_id=1, name="候选A", distance_m=100.0, floor_diff=0,
                business_status="open", has_promotion=False,
                recommend_weight=1.0, hot_score=50.0, tags=["安静"],
                trunk_dist_m=10.0)
    base.update(kw)
    return base


CTX = {"tags": ["安静"], "n_candidates": 2}


# ---------- 因子公式 ----------

def test_distance_factor_formula():
    fs = factor_scores(cand(distance_m=500.0), CTX)
    assert fs["distance"] == pytest.approx(0.5)
    fs = factor_scores(cand(distance_m=1500.0), CTX)
    assert fs["distance"] == pytest.approx(0.0), "超过 1000m 记 0"


def test_floor_diff_formula():
    assert factor_scores(cand(floor_diff=2), CTX)["floor_diff"] == pytest.approx(0.6)
    assert factor_scores(cand(floor_diff=5), CTX)["floor_diff"] == pytest.approx(0.0)


def test_business_status_open_and_closing():
    assert factor_scores(cand(), CTX)["business"] == pytest.approx(1.0)
    closing = factor_scores(cand(business_status="closing_soon"), CTX)
    assert closing["business"] == pytest.approx(0.4)


def test_closed_candidate_filtered_out():
    ranked = score_candidates([cand(), cand(poi_id=2, business_status="closed")], CTX)
    assert [r["poi_id"] for r in ranked] == [1], "休息中的候选直接过滤（PRD 8.4）"


def test_promotion_flag():
    assert factor_scores(cand(has_promotion=True), CTX)["promotion"] == pytest.approx(1.0)
    assert factor_scores(cand(), CTX)["promotion"] == pytest.approx(0.0)


def test_minmax_normalization_hot_and_weight():
    c_low = cand(poi_id=1, hot_score=10.0, recommend_weight=1.0)
    c_high = cand(poi_id=2, hot_score=20.0, recommend_weight=2.0)
    fs_low = factor_scores(c_low, CTX, all_candidates=[c_low, c_high])
    fs_high = factor_scores(c_high, CTX, all_candidates=[c_low, c_high])
    assert fs_low["hot"] == pytest.approx(0.0) and fs_high["hot"] == pytest.approx(1.0)
    assert fs_low["merchant"] == pytest.approx(0.0) and fs_high["merchant"] == pytest.approx(1.0)


def test_minmax_all_equal_is_neutral():
    fs = factor_scores(cand(), CTX, all_candidates=[cand()])
    assert fs["hot"] == pytest.approx(0.5) and fs["merchant"] == pytest.approx(0.5)


def test_tag_match_ratio():
    ctx = {"tags": ["安静", "约会", "亲子"]}
    two_of_three = factor_scores(cand(tags=["安静", "亲子", "数码"]), ctx)
    assert two_of_three["tag_match"] == pytest.approx(2 / 3)
    assert factor_scores(cand(tags=[]), ctx)["tag_match"] == pytest.approx(0.0)
    no_tags = factor_scores(cand(), {"tags": []})
    assert no_tags["tag_match"] == pytest.approx(0.5), "意图无标签时中性"


def test_convenience_trunk_distance():
    assert factor_scores(cand(trunk_dist_m=0.0), CTX)["convenience"] == pytest.approx(1.0)
    assert factor_scores(cand(trunk_dist_m=300.0), CTX)["convenience"] == pytest.approx(0.0)


# ---------- 加权与排序 ----------

def test_weights_sum_to_one():
    assert sum(DEFAULT_WEIGHTS.values()) == pytest.approx(1.0)


def test_score_is_weighted_sum():
    fs = factor_scores(cand(distance_m=500.0), CTX)  # distance=0.5
    from recommender.scoring import weighted_score

    assert weighted_score(fs, DEFAULT_WEIGHTS) == pytest.approx(
        sum(fs[k] * w for k, w in DEFAULT_WEIGHTS.items()))


def test_higher_score_first_and_fields_present():
    good = cand(poi_id=1, distance_m=50.0, has_promotion=True)
    bad = cand(poi_id=2, distance_m=900.0)
    ranked = score_candidates([bad, good], CTX)
    assert [r["poi_id"] for r in ranked] == [1, 2]
    for row in ranked:
        assert set(row) >= {"poi_id", "score", "factors", "reasons"}
        assert len(row["factors"]) == 8, "八个因子明细全量可见"


def test_reasons_max_three_and_readable():
    ranked = score_candidates(
        [cand(has_promotion=True, distance_m=10.0, hot_score=99.0)], CTX)
    reasons = ranked[0]["reasons"]
    assert 1 <= len(reasons) <= 3 and all(isinstance(r, str) and r for r in reasons)


def test_empty_candidates_returns_empty():
    assert score_candidates([], CTX) == []


# ---------- 权重配置文件（F-16：固定配置，不做后台可调） ----------

def test_weights_loadable_from_yaml():
    w = LoadableWeights.default()
    assert w.as_dict()["distance"] == pytest.approx(0.22)
    assert abs(sum(w.as_dict().values()) - 1.0) < 1e-9
