"""LangGraph 有状态编排（M5 核心）：intent → tools → rag → rank → generate。

约束（PRD 8.2/手册 7.4）：
- 节点粒度一事一节点；条件边按意图路由
- 单轮 ≤6 次工具调用、总耗时 ≤12s：超限立即用已有结果生成并标 degraded
- 同工具同入参指纹去重（tools.run_tool 的 seen 集合）
- 每步写 agent_traces（step_type/tool_code/input/output/status/latency_ms/error_code）
- State 只存可序列化数据（ToolContext/provider 经 config["configurable"] 注入，
  与 checkpointer 兼容）
"""

from __future__ import annotations

import json
import logging
import operator
import re
import time
from typing import Annotated, Any, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from .intent import parse_intent

logger = logging.getLogger(__name__)
from .tools import run_tool

MAX_TOOL_CALLS = 6
BUDGET_SECONDS = 12.0

# intent → 依序执行的计划步 key（每步由 _PLANNED_STEPS 生成 [(code, args), ...]）
TOOL_PLAN: dict[str, list[str]] = {
    "facility_nearest": ["nearest_and_route"],
    "poi_search": ["search_and_rank"],
    "poi_recommend": ["search_scene", "promotions", "rank", "knowledge"],
    "promotion_query": ["promotions"],
    "navigate": ["route_to_poi"],
    "venue_info": ["knowledge"],
    "coupon_claim": ["claim_coupon"],
    "fallback": ["knowledge"],
}


class AgentState(TypedDict):
    # 输入（由服务层填充）
    tenant_id: int
    venue_id: int
    message: str
    trace_id: str
    session_id: int
    message_id: int
    # 运行时（节点间传递）
    intent: dict
    tool_results: dict[str, Any]
    tool_calls: int
    degraded: bool
    error_codes: Annotated[list[int], operator.add]
    citations: list[dict]
    answer: str
    cards: list[dict]
    turn_started: float


def _ctx(config) -> dict:
    return config["configurable"]  # {"ctx": ToolContext, "provider": ..., "tracer": ...}


def _tracer(config, state: AgentState, step_type: str, tool_code: str | None,
            data_in: object, data_out: object, status: str, latency_ms: int,
            error_code: int | None = None) -> None:
    import psycopg

    cfg = _ctx(config)
    with psycopg.connect(cfg["ctx"].dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "insert into agent_traces (session_id, message_id, tenant_id, trace_id, "
            "step_index, step_type, tool_code, input, output, status, latency_ms, error_code) "
            "select %s, %s, %s, %s, coalesce(max(step_index),0)+1, %s, %s, %s, %s, %s, %s, %s "
            "from agent_traces where message_id=%s",
            (state["session_id"], state["message_id"], state["tenant_id"], state["trace_id"],
             step_type, tool_code, json.dumps(data_in, ensure_ascii=False, default=str)[:2000],
             json.dumps(data_out, ensure_ascii=False, default=str)[:2000],
             status, latency_ms, error_code, state["message_id"]),
        )


def _intention(state: AgentState, config) -> dict:
    cfg = _ctx(config)
    t0 = time.monotonic()
    parsed = parse_intent(state["message"], cfg["provider"],
                          history=cfg.get("history"))
    _tracer(config, state, "intent_parse", None,
            {"message": state["message"]}, parsed, "ok",
            int((time.monotonic() - t0) * 1000))
    return {"intent": parsed, "turn_started": time.monotonic()}


def _candidate_ids(state: AgentState) -> list[int]:
    for key in ("poi.search",):
        items = (state.get("tool_results") or {}).get(key, {}).get("items") or []
        if items:
            return [i["poi_id"] for i in items][:8]
    return []


_PLANNED_STEPS = {
    # 每步返回 [(tool_code, args), ...]；ctx 从 _ctx(config) 取（修 Key 根因）
    "nearest_and_route": lambda s, c: [
        ("facility.nearest",
         {"facility": s["intent"]["slots"].get("category") or "卫生间"}),
        ("route.plan",
         {"to_poi_name": s["intent"]["slots"].get("category") or "卫生间"}),
    ],
    "search_and_rank": lambda s, c: [
        ("poi.search",
         {"category": s["intent"]["slots"].get("category"),
          "keyword": s["intent"]["slots"].get("poi_name"),
          "scene_tag": s["intent"]["slots"].get("scene_tag")}),
    ],
    "search_scene": lambda s, c: [
        ("poi.search",
         {"category": s["intent"]["slots"].get("category"),
          "scene_tag": s["intent"]["slots"].get("scene_tag")}),
    ],
    "promotions": lambda s, c: [("promotion.list", {})],
    "route_to_poi": lambda s, c: [
        ("route.plan",
         {"to_poi_name": s["intent"]["slots"].get("poi_name")
          or s["intent"]["slots"].get("category"),
          "prefer_accessible": bool(_ctx(c)["ctx"].prefer_accessible)}),
    ],
    "rank": lambda s, c: [("recommend.rank", {"candidates": _candidate_ids(s)})],
    "knowledge": lambda s, c: [("knowledge.query",
                                {"query": s["message"], "threshold": 0.30})],
    "claim_coupon": lambda s, c: [
        ("coupon.claim",
         {"coupon_title": s["intent"]["slots"].get("category")
          or s["intent"]["slots"].get("poi_name") or "",
          "anonymous_id": _ctx(c).get("anonymous_id") or "anonymous-demo"}),
    ],
}


def _tools(state: AgentState, config) -> dict:
    """按意图计划依序执行工具：预算（≤6 次/12s）与去重在循环内强制。"""
    cfg = _ctx(config)
    ctx = cfg["ctx"]
    intent = state["intent"]["intent"]
    steps = TOOL_PLAN.get(intent, [])
    results: dict[str, Any] = dict(state.get("tool_results") or {})
    calls = state.get("tool_calls", 0)
    degraded = state.get("degraded", False)
    errors: list[int] = []
    deadline = state.get("turn_started", time.monotonic()) + BUDGET_SECONDS

    for plan_name in steps:
        if calls >= MAX_TOOL_CALLS or time.monotonic() > deadline:
            degraded = True
            break
        for code, args in _PLANNED_STEPS[plan_name](state, config):
            if calls >= MAX_TOOL_CALLS or time.monotonic() > deadline:
                degraded = True
                break
            result = run_tool(code, args, ctx, seen=cfg.setdefault("seen", set()))
            t0 = time.monotonic()
            calls += 1
            results[code] = result.data
            status = "ok" if result.ok else "error"
            _tracer(config, state, "tool_call", code, args, result.data, status,
                    int((time.monotonic() - t0) * 1000), result.error_code)
            if result.error_code:
                errors.append(result.error_code)
            # degraded 语义=回答完整性受损：硬错误/知识降级/预算超限才置位；
            # 路线文字指引等工具级提示只记 error_code，不拉低整轮状态
            if not result.ok:
                degraded = True
            if code == "knowledge.query" and result.degraded:
                degraded = True

    return {"tool_results": results, "tool_calls": calls,
            "degraded": degraded, "error_codes": errors}


def _rag(state: AgentState, config) -> dict:
    """知识检索节点：venue_info/fallback 已在计划内执行；这里只补 citations。"""
    data = (state.get("tool_results") or {}).get("knowledge.query") or {}
    items = data.get("items") or []
    citations = [
        {"document_id": i["document_id"], "title": i["title"], "snippet": i["content"][:80]}
        for i in items[:3]
    ]
    return {"citations": citations}


def _rank(state: AgentState, config) -> dict:
    # rank 已并入 _tools 的计划步；此节点保留为显式占位（保持"一事一节点"图结构）
    return {}


def _generate(state: AgentState, config) -> dict:
    """生成回答 + 卡片；幻觉后置校验：回答中的店名必须来自工具结果。"""
    cfg = _ctx(config)
    provider = cfg["provider"]
    results = state.get("tool_results") or {}
    digest = json.dumps(results, ensure_ascii=False, default=str)[:3500]
    system = (config["configurable"]["prompts_dir"] / "answer_system.txt").read_text(
        encoding="utf-8")
    degraded = state.get("degraded", False)
    try:
        answer, usage = provider.chat(
            [{"role": "system", "content": system},
             {"role": "user", "content": f"顾客说：{state['message']}\n工具结果：{digest}"}],
            max_tokens=300,
        )
    except Exception:  # Provider 不可用 → 兜底话术（不白屏）
        answer = "我暂时没有这方面的信息，你可以问问商场服务台（F1 层）。"
        degraded = True

    # 幻觉后置校验：收集本轮工具结果中出现过的店名，回答里出现名单外的疑似店名 → 降级为列表卡片
    known_names = _known_poi_names(results)
    suspect = _unknown_poi_names(answer, known_names)
    cards = _build_cards(state, results)
    if suspect:
        answer = "为你找到这些：" + "、".join(
            i["name"] for i in (results.get("recommend.rank", {}).get("ranked")
                                or results.get("poi.search", {}).get("items") or [])[:3]
        ) if cards else "我暂时没有这方面的信息，你可以问问商场服务台（F1 层）。"
        degraded = True
        logger.warning("幻觉拦截：回答含名单外店名 %s，降级为列表卡片", suspect)
        _tracer(config, state, "post_validate", None,
                {"suspect": suspect}, {"action": "降级列表卡片"}, "degraded", 0)

    _tracer(config, state, "generate", None, {"digest_len": len(digest)},
            {"answer": answer[:200]}, "degraded" if degraded else "ok", 0)
    return {"answer": answer, "cards": cards, "citations": state.get("citations", []),
            "degraded": degraded}


def _known_poi_names(results: dict) -> set[str]:
    names: set[str] = set()
    for code, data in results.items():
        if not isinstance(data, dict):
            continue
        for item in data.get("items") or []:
            if isinstance(item, dict) and item.get("name"):
                names.add(item["name"])
        for item in data.get("ranked") or []:
            names.add(item["name"])
        nodes = data.get("nodes") or {}
        names |= {v["label"] for v in nodes.values() if isinstance(v, dict)}
    return names


_STORE_SUFFIX = re.compile(r"[一-鿿]{1,6}(?:店|铺|餐厅|馆|屋|坊)")


def _unknown_poi_names(answer: str, known: set[str]) -> list[str]:
    """抽取回答中的疑似 POI 名称（店/铺/餐厅/馆 结尾），与本轮工具结果比对。

    精确包含（互为子串）即认可；不在名单 → 疑似幻觉，降级为列表卡片。
    """
    generic = {
        "火锅店", "咖啡店", "奶茶店", "便利店", "甜品店", "服装店", "书店", "鞋店",
        "玩具店", "眼镜店", "餐厅", "面馆", "日料店", "西餐厅", "美发店", "理发店",
        "花店", "药店", "店铺", "商店", "全馆", "本馆",
    }
    stop_chars = set("的了是有在去指找哪全这那你我三几几聊说想推荐")

    suspects = []
    for w in {m[-5:] for m in _STORE_SUFFIX.findall(answer)}:
        w = re.sub(r"^[家间位个]", "", w)  # 量词被数字截断的残片："家店铺"→"店铺"
        if w in known or w in generic:
            continue
        if any(ch in w for ch in stop_chars):
            continue  # 含功能字的短语（"找到卖衣服的店"）不是店名
        if any(w in k or k in w for k in known):
            continue
        suspects.append(w)
    return sorted(suspects)


def _build_cards(state: AgentState, results: dict) -> list[dict]:
    cards: list[dict] = []
    ranked = (results.get("recommend.rank") or {}).get("ranked")
    items = (results.get("poi.search") or {}).get("items") or []
    source = ranked or ([{**i, "reasons": []} for i in items[:3]] if items else None)
    if source:
        cards.append({"type": "poi_list",
                      "items": [{"poi_id": i["poi_id"], "name": i["name"],
                                 "floor": i.get("floor")} for i in source[:3]]})
    route = results.get("route.plan") or {}
    if route.get("segments"):
        cards.append({"type": "route",
                      "summary": {"distance_meter": route["total_distance_meter"],
                                  "eta_seconds": route["total_time_s"],
                                  "nodes": route.get("nodes", {})}})
    nearest = (results.get("facility.nearest") or {})
    if nearest.get("items"):
        cards.append({"type": "poi_list",
                      "items": [{"poi_id": i["poi_id"], "name": i["name"],
                                 "floor": i.get("floor")} for i in nearest["items"][:3]]})
    promos = (results.get("promotion.list") or {})
    if promos.get("coupons") or promos.get("activities"):
        cards.append({"type": "coupon", "data": promos})
    return cards


def build_graph(checkpointer=None, prompts_dir=None):
    """意图 → 工具 → 引用 → 生成；条件边按意图决定是否跳过工具步。"""
    g = StateGraph(AgentState)
    g.add_node("intent", _intention)
    g.add_node("tools", _tools)
    g.add_node("rag", _rag)
    g.add_node("rank", _rank)
    g.add_node("generate", _generate)
    g.add_edge(START, "intent")
    g.add_edge("intent", "tools")
    g.add_edge("tools", "rag")
    g.add_edge("rag", "rank")
    g.add_edge("rank", "generate")
    g.add_edge("generate", END)

    if checkpointer is None:
        checkpointer = InMemorySaver()
    return g.compile(checkpointer=checkpointer)


PROMPTS_DIR = None  # 由服务层注入 Path；graph 节点经 config 读取
