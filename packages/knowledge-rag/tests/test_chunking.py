"""切片器单测：token 估算、段落边界、300-500 上限、重叠 50。"""

from __future__ import annotations

from knowledge_rag.chunking import estimate_tokens, split_into_chunks


def test_estimate_tokens_cjk_and_ascii():
    assert estimate_tokens("火锅火锅火锅") == 6          # CJK 1 字 1 token
    assert estimate_tokens("abcdefgh") == 2              # 8/4
    assert estimate_tokens("火锅abc") == 3               # 2 + ceil(3/4)=1
    assert estimate_tokens("") == 0


def test_short_doc_single_chunk():
    doc = "本店提供云雾系列手冲咖啡。" * 5
    chunks = split_into_chunks(doc)
    assert len(chunks) == 1
    assert estimate_tokens(chunks[0]) <= 500


def test_long_doc_multiple_chunks_with_limits():
    para = "这是一段足够长的店铺介绍，" * 40  # ~240 tokens/段
    doc = "\n\n".join(para for _ in range(8))
    chunks = split_into_chunks(doc)
    assert len(chunks) >= 2
    for c in chunks:
        assert estimate_tokens(c) <= 500, f"chunk 超上限：{estimate_tokens(c)}"
        assert estimate_tokens(c) > 0


def test_overlap_present_between_adjacent_chunks():
    para = "云雀灶火锅位于二层，主打鲜切牛羊肉与手工丸滑，" * 30
    doc = "\n\n".join(para for _ in range(6))
    chunks = split_into_chunks(doc)
    assert len(chunks) >= 2
    tail = chunks[0][-30:]
    assert chunks[1].startswith(tail) or any(
        chunks[0][-30:] in chunks[1][:120] for _ in [0]
    ), "相邻块应有重叠"


def test_paragraph_boundary_respected():
    p1 = "第一段：营业时间每天十点到十点。" * 3
    p2 = "第二段：停车场位于地下一层。" * 3
    doc = p1 + "\n\n" + p2
    chunks = split_into_chunks(doc)
    joined = "\n".join(chunks)
    assert "第一段" in joined and "第二段" in joined
    # 两个短段应合并进同一块（合计 < 300 token）
    assert len(chunks) == 1


def test_trailing_small_chunk_merged():
    big = "甲" * 1200   # ~1200 tokens → 至少 3 块
    small = "乙" * 10
    chunks = split_into_chunks(big + "\n\n" + small)
    assert estimate_tokens(chunks[-1]) > 50 or len(chunks) == 1, "末块过短应并入前块"
