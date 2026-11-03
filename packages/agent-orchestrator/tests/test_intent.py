"""意图解析节点单测（桩 provider，无网络）：合法/带围栏/重试/回落。"""

from __future__ import annotations

import json

from agent_orchestrator.intent import parse_intent


class FakeChat:
    def __init__(self, replies: list[str]):
        self.replies = list(replies)
        self.calls = 0

    def chat(self, messages, **_kw):
        self.calls += 1
        reply = self.replies[min(self.calls - 1, len(self.replies) - 1)]
        return reply, {"tokens_in": 1, "tokens_out": 1}


VALID = json.dumps({"intent": "poi_search",
                    "slots": {"category": "火锅", "scene_tag": None, "poi_name": None,
                              "need_route": False}})


def test_valid_json_parsed():
    r = parse_intent("我想吃火锅", FakeChat([VALID]))
    assert r["intent"] == "poi_search" and r["slots"]["category"] == "火锅"
    assert r["retries"] == 0


def test_code_fence_stripped():
    r = parse_intent("x", FakeChat([f"```json\n{VALID}\n```"]))
    assert r["intent"] == "poi_search"


def test_retry_once_then_success():
    r = parse_intent("x", FakeChat(["不是JSON", VALID]))
    assert r["intent"] == "poi_search" and r["retries"] == 1


def test_double_failure_falls_back():
    r = parse_intent("x", FakeChat(["垃圾输出"]))
    assert r["intent"] == "fallback" and r["retries"] == 2


def test_invalid_intent_enum_falls_back():
    bad = json.dumps({"intent": "super_search", "slots": {}})
    r = parse_intent("x", FakeChat([bad]))
    assert r["intent"] == "fallback"
