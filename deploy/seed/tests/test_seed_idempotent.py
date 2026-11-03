"""seed 幂等性验收：连续执行两遍各表行数完全一致，并断言已交付子任务的最小规模。

需要 DATABASE_URL 与 SEED_DEMO_ADMIN_PASSWORD（conftest 自动读 .env）。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SEED_PY = Path(__file__).resolve().parents[1] / "seed.py"


@pytest.fixture(scope="module")
def seed_mod():
    spec = importlib.util.spec_from_file_location("sage_seed", SEED_PY)
    assert spec and spec.loader, "无法加载 deploy/seed/seed.py"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_seed_twice_same_counts(seed_mod):
    counts1 = seed_mod.run_seed()
    counts2 = seed_mod.run_seed()
    assert counts1 == counts2, f"seed 不幂等：\n第一遍 {counts1}\n第二遍 {counts2}"


def test_identity_and_space_scale(seed_mod):
    counts = seed_mod.run_seed()
    assert counts["tenants"] == 1, "demo 只演示 1 家租户（ARCHITECTURE 2.4）"
    assert counts["venues"] == 1
    assert counts["floors"] == 3, "B1/F1/F2 三层"
    assert counts["map_layers"] == 3
    assert counts["users"] == 3, "M1 演示账号 3 个（venue_admin/venue_editor/merchant）"
    assert counts.get("user_roles") == 3, "每个演示账号恰一条角色绑定"
    assert counts.get("devices") == 1, "M1 演示设备 1 台（screen-f1-01）"
    assert counts["roles"] == 5, "PRD 6.1 五个角色字典"
    assert counts["poi_categories"] >= 25, "分类字典应覆盖餐饮/零售/娱乐/设施"
    assert counts["pois"] == 88, "68 店铺 + 20 设施"
    assert counts["activities"] + counts["coupons"] == 10, "活动与优惠合计 10 条"
    assert counts["knowledge_documents"] == 100, "100 篇知识文档（68 介绍+17 指南+15 FAQ）"
