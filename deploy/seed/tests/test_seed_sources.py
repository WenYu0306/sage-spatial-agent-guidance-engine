"""seed 数据源 YAML 的结构校验（不连数据库）。

规模断言随 ③（店铺+设施）、④（活动/知识库）、⑤（评测基线）的数据文件补齐而扩展。
"""

from __future__ import annotations

import re
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
    assert "cinema" in code_set, "影院分类必须有（附录 B 问句 6）"


def test_pois_files_structure():
    """三层店铺文件 + 设施文件：坐标边界/同层不重合/分类存在/营业时间格式/标签非空。"""
    cats = _load("poi_categories.yaml")
    code_set = {c["code"] for c in cats["categories"]}
    facility_cats = {c["code"] for c in cats["categories"] if c.get("is_facility")}

    all_pois: list[dict] = []
    for fname in ("pois_b1.yaml", "pois_f1.yaml", "pois_f2.yaml"):
        data = _load(fname)
        floor = data.get("floor")
        assert floor in {"B1", "F1", "F2"}, f"{fname} 缺 floor 字段"
        for p in data["pois"]:
            p["_floor"] = floor
            p["_src"] = fname
            all_pois.append(p)

    fac = _load("facilities.yaml")
    assert len(fac["pois"]) == 20, "设施必须恰好 20 处（手册 7.2 要求 2）"
    for p in fac["pois"]:
        p["_floor"] = p["floor"]
        p["_src"] = "facilities.yaml"
        all_pois.append(p)

    seen: dict[tuple, str] = {}
    for p in all_pois:
        name, floor = p["name"], p["_floor"]
        x, y = float(p["x"]), float(p["y"])
        assert 0 < x < 1200 and 0 < y < 800, f"{name} 坐标越界：({x},{y})"
        assert p["category"] in code_set, f"{name} 分类 {p['category']} 不在字典中"
        assert p["category"] not in facility_cats or p["_src"] == "facilities.yaml", (
            f"{name} 用了设施分类却不在设施文件中"
        )

        assert re.fullmatch(r"\d{2}:\d{2}-\d{2}:\d{2}", str(p["hours"])), (
            f"{name} 营业时间格式应为 HH:MM-HH:MM"
        )
        assert p.get("tags"), f"{name} 缺标签（AI 场景匹配依赖）"
        assert 0 <= float(p.get("hot", 0)) <= 100, f"{name} hot_score 越界"
        key = (floor, x, y)
        assert key not in seen, f"同层坐标重复：{name} 与 {seen[key]}"
        seen[key] = name

    stores = [p for p in all_pois if p["_src"] != "facilities.yaml"]
    assert 60 <= len(stores) <= 80, f"店铺数 {len(stores)} 应在 60—80（手册 7.2 要求 2）"


def test_activities_structure():
    """活动+优惠券合计 10 条；poi 引用必须存在于店铺文件；时间区间合法。"""
    data = _load("activities.yaml")
    acts, coupons = data["activities"], data["coupons"]
    assert len(acts) + len(coupons) == 10, "活动与优惠合计 10 条（手册 7.2 要求 2）"

    store_names = set()
    for fname in ("pois_b1.yaml", "pois_f1.yaml", "pois_f2.yaml"):
        store_names |= {p["name"] for p in _load(fname)["pois"]}
    for a in acts:
        assert a["title"] and a["act_type"], "活动缺 title/act_type"
        assert a["start_at"] < a["end_at"], f"{a['title']} 时间区间倒挂"
        if a.get("poi"):
            assert a["poi"] in store_names, f"{a['title']} 引用不存在的店铺 {a['poi']}"
    for c in coupons:
        assert c["title"] and c["coupon_type"] in {"discount", "full_reduction", "gift"}
        if c["coupon_type"] == "full_reduction":
            assert c.get("threshold", 0) > c.get("value", 0), f"{c['title']} 满减门槛应大于减免额"
        if c.get("poi"):
            assert c["poi"] in store_names, f"{c['title']} 引用不存在的店铺 {c['poi']}"

    # 附录 B 问句 16 依赖满 100 减 20 的券
    full100 = [c for c in coupons if c.get("threshold") == 100 and c.get("value") == 20]
    assert full100, "缺满 100 减 20 券（附录 B 问句 16 的基线依赖）"


def test_knowledge_files_structure():
    """场地指南 17 篇 + FAQ 15 篇（其余 68 篇店铺介绍由 seed 从 pois 生成，合计 100）。"""
    guides = _load("knowledge_venue.yaml")["docs"]
    faqs = _load("knowledge_faq.yaml")["docs"]
    assert len(guides) == 17, f"场地指南应 17 篇，实际 {len(guides)}"
    assert len(faqs) == 15, f"FAQ 应 15 篇，实际 {len(faqs)}"
    for d in guides + faqs:
        assert d["doc_type"] in {"venue_guide", "faq"}
        assert d["title"] and len(d["content"]) >= 20, f"{d['title']} 内容过短"
    titles = [d["title"] for d in guides + faqs]
    assert len(titles) == len(set(titles)), "指南/FAQ 标题不得重复"


def test_eval_baseline_structure():
    """评测基线：20 问句对齐附录 B；意图/工具枚举对齐 PRD 8.1/8.2。"""
    data = _load("eval_baseline.yaml")
    cases = data["cases"]
    assert len(cases) == 20, f"评测问句应 20 条，实际 {len(cases)}"
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids)), "评测问句 id 不得重复"
    intents = {"facility_nearest", "poi_search", "poi_recommend", "promotion_query",
               "navigate", "venue_info", "coupon_claim", "fallback"}
    tools = {"poi.search", "route.plan", "facility.nearest", "promotion.list",
             "knowledge.query", "recommend.rank", "coupon.claim", "poi.detail"}
    for c in cases:
        assert c["question"], f"{c['id']} 缺问句"
        assert c["intent"] in intents, f"{c['id']} 意图 {c['intent']} 不在 PRD 8.1 枚举"
        assert set(c["tools"]) <= tools, f"{c['id']} 工具链不在 PRD 8.2 八工具内"
        assert c["answer_keys"], f"{c['id']} 缺期望答案要点"
    questions = [c["question"] for c in cases]
    assert "帮我领那张满 100 减 20 的券" in questions, "必须含附录 B 问句 16"
    assert "今天有什么优惠" in questions, "必须含附录 B 问句 5"
    e19 = next(c for c in cases if c["question"].startswith("今天天气"))
    assert e19["intent"] == "fallback", "天气问句必须走 fallback（不编造）"
    e12 = next(c for c in cases if "三楼" in c["question"])
    assert e12.get("notes"), "E12 缺处理说明（demo 无 F3，须记录解析策略）"
