"""意图解析节点：LLM 结构化输出（JSON Schema 校验，失败重试 1 次，禁止正则硬编码）。

prompt 存配置文件 prompts/intent_system.txt（CLAUDE.md：prompt 不硬编码）。
解析失败重试 1 次后仍失败 → 回落 fallback 意图（不抛错、不中断会话）。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import jsonschema

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "intent_system.txt"

INTENTS = (
    "facility_nearest", "poi_search", "poi_recommend", "promotion_query",
    "navigate", "venue_info", "coupon_claim", "fallback",
)

INTENT_SCHEMA = {
    "type": "object",
    "required": ["intent", "slots"],
    "properties": {
        "intent": {"type": "string", "enum": list(INTENTS)},
        "slots": {
            "type": "object",
            "properties": {
                "category": {"type": ["string", "null"]},
                "scene_tag": {"type": ["string", "null"]},
                "poi_name": {"type": ["string", "null"]},
                "need_route": {"type": ["boolean", "null"]},
            },
        },
    },
}

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> dict:
    """容忍 ```json 围栏与前后噪声，取第一个平衡的 JSON 对象。"""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):] if "{" in text else text
    start = text.find("{")
    if start == -1:
        raise ValueError("输出中无 JSON 对象")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise ValueError("JSON 未闭合")


def parse_intent(text: str, provider, history: list[dict] | None = None) -> dict:
    """解析意图；返回 {"intent", "slots", "retries"}。两次失败回落 fallback。"""
    system = PROMPT_PATH.read_text(encoding="utf-8")
    messages = [{"role": "system", "content": system}]
    messages.extend(history or [])
    messages.append({"role": "user", "content": text})

    last_error = ""
    for attempt in range(2):
        if attempt:
            retry_msg = f"上面的输出不是合法 JSON（{last_error}），重新只输出 JSON。"
            call = messages + [{"role": "user", "content": retry_msg}]
        else:
            call = messages
        raw, usage = provider.chat(call)
        try:
            data = _extract_json(raw)
            jsonschema.validate(data, INTENT_SCHEMA)
            data["retries"] = attempt
            data["usage"] = usage
            return data
        except (ValueError, json.JSONDecodeError, jsonschema.ValidationError) as exc:
            last_error = str(exc)[:120]
            logger.warning("意图解析失败(%s/2)：%s", attempt + 1, last_error)
    return {"intent": "fallback", "slots": {}, "retries": 2,
            "usage": {"tokens_in": 0, "tokens_out": 0}}
