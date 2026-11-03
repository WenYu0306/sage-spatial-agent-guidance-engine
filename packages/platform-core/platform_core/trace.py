"""trace_id 生成与传递（ARCHITECTURE 3.2 第 5 条：端层生成、贯穿全程、落库可查）。"""

from __future__ import annotations

import uuid

PREFIX = "tr_"


def new_trace_id() -> str:
    """tr_ + uuid4 前 12 位；全局唯一且日志可 grep。"""
    return PREFIX + uuid.uuid4().hex[:12]


def is_valid_trace_id(value: str) -> bool:
    return value.startswith(PREFIX) and len(value) == len(PREFIX) + 12
