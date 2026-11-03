"""seed 数据源 YAML 的结构校验（不连数据库）。

规模断言随 ③（店铺+设施）、④（活动/知识库）、⑤（评测基线）的数据文件补齐而扩展。
"""

from __future__ import annotations

from pathlib import Path

import yaml

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _load(name: str) -> dict:
    path = DATA_DIR / name
    assert path.exists(), f"缺数据源文件 data/{name}（按子任务计划补齐）"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_tenant_venue_structure():
    data = _load("tenant_venue.yaml")
    tenant, venue, floors = data["tenant"], data["venue"], data["floors"]
    assert tenant["code"] and tenant["name"], "租户必须虚构名称与编码"
    assert venue["venue_type"] == "mall"
    assert len(floors) == 3, "手册 7.2 要求 3 层"
    levels = [f["level"] for f in floors]
    assert len(set(levels)) == 3, "楼层 level 不得重复"
    assert min(levels) < 0 < max(levels), "须含地下层（B1=-1）与地上层"
    assert sum(1 for f in floors if f["is_default"]) == 1, "默认楼层必须恰好 1 个"
    layer_names = set(data["map_layers"])
    assert layer_names == {f["name"] for f in floors}, "每个楼层都要有底图层"
    for layer in data["map_layers"].values():
        assert layer["width"] > 0 and layer["height"] > 0
        assert 0 < float(layer["scale_meter"]) < 1, "1 SVG 单位应小于 1 米（商场尺度）"


def test_poi_categories_structure():
    data = _load("poi_categories.yaml")
    cats = data["categories"]
    codes = [c["code"] for c in cats]
    assert len(codes) == len(set(codes)), "分类 code 必须唯一"
    code_set = set(codes)
    for c in cats:
        assert c.get("name"), f"{c['code']} 缺中文名"
        assert isinstance(c.get("sort_order"), int), f"{c['code']} sort_order 必须是整数"
        if c.get("parent_code"):
            assert c["parent_code"] in code_set, f"{c['code']} 的 parent_code 不存在"
    facilities = {c["code"] for c in cats if c.get("is_facility")}
    assert {"toilet", "nursing_room", "elevator", "info_desk", "parking"} <= facilities, (
        "设施分类必须覆盖卫生间/母婴室/电梯/服务台/停车场（附录 B 评测问句依赖）"
    )
    assert "supermarket" in code_set, "超市分类必须有（附录 B 问句 18）"
    assert "hotpot" in code_set, "火锅分类必须有（附录 B 问句 3）"
