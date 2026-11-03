"""切片器（纯函数）：300—500 token、重叠 50、段落边界优先。

token 估算规则（可讲、无需分词器）：CJK 每字 ≈1 token，其余每 4 字符 ≈1 token。
规则：按空行分段 → 贪心装段（不超 MAX）→ 单段超限按句切、再按字符硬切 →
相邻块保留上一块尾部 ~50 token 作重叠 → 末块过短并入前块。
"""

from __future__ import annotations

import re

MIN_TOKENS = 300
MAX_TOKENS = 500
OVERLAP_TOKENS = 50


def estimate_tokens(text: str) -> int:
    cjk = sum(1 for ch in text if "一" <= ch <= "鿿")
    other = len(text) - cjk
    return cjk + (other + 3) // 4


def _hard_split(text: str, max_tokens: int) -> list[str]:
    """单段超限：先按句（。！？!?.）切，仍超限再按字符硬切。"""
    sentences = re.findall(r"[^。！？!?.]*[。！？!?.]?", text)
    parts: list[str] = []
    buf = ""
    for sen in sentences:
        if not sen:
            continue
        if estimate_tokens(buf + sen) > max_tokens and buf:
            parts.append(buf)
            buf = sen
        else:
            buf += sen
        while estimate_tokens(buf) > max_tokens:  # 单句仍超限 → 字符硬切
            cut = len(buf) // 2
            parts.append(buf[:cut])
            buf = buf[cut:]
    if buf:
        parts.append(buf)
    return parts


def _tail_overlap(text: str, overlap_tokens: int) -> str:
    """取尾部约 overlap_tokens 的文本（按字符逐步回退直到超限）。"""
    chars = list(text)
    n = len(chars)
    while n > 0 and estimate_tokens("".join(chars[-n:])) > overlap_tokens:
        n -= max(1, n // 10)
    return "".join(chars[-n:])


def split_into_chunks(content: str) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", content) if p.strip()]
    pieces: list[str] = []
    for para in paras:
        if estimate_tokens(para) > MAX_TOKENS:
            pieces.extend(_hard_split(para, MAX_TOKENS))
        else:
            pieces.append(para)

    chunks: list[str] = []
    buf = ""
    for piece in pieces:
        cand = f"{buf}\n\n{piece}" if buf else piece
        if estimate_tokens(cand) > MAX_TOKENS and buf:
            chunks.append(buf)
            buf = piece
        else:
            buf = cand
    if buf:
        chunks.append(buf)

    # 相邻块重叠：前块尾部拼到后块头部
    overlapped: list[str] = []
    for i, c in enumerate(chunks):
        if i == 0:
            overlapped.append(c)
            continue
        # 重叠预算：目标 50 token，但拼接后不得超过 MAX
        budget = min(OVERLAP_TOKENS, max(0, MAX_TOKENS - estimate_tokens(c)))
        tail = _tail_overlap(chunks[i - 1], budget) if budget > 0 else ""
        overlapped.append(f"{tail}{c}" if tail else c)

    # 末块过短 → 并入前块（合并后仍 ≤ MAX 才并，否则保留）
    if len(overlapped) >= 2:
        last = overlapped[-1]
        prev = overlapped[-2]
        if estimate_tokens(last) < MIN_TOKENS and estimate_tokens(prev + last) <= MAX_TOKENS:
            overlapped = overlapped[:-2] + [prev + last]
    return overlapped
