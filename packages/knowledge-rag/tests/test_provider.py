"""Provider 抽象单测：env 配置、每日上限、mock 确定性向量、SDK 调用桩。"""

from __future__ import annotations

import pytest
from knowledge_rag.provider import (
    DailyLimitError,
    LLMProvider,
    MockProvider,
    ProviderConfig,
    ProviderUnavailableError,
)


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://x/v1")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("EMBEDDING_MODEL", "m-embed")
    monkeypatch.setenv("EMBED_DIM", "8")
    monkeypatch.setenv("LLM_DAILY_LIMIT", "3")
    cfg = ProviderConfig.from_env()
    assert cfg.base_url == "http://x/v1"
    assert cfg.embedding_model == "m-embed"
    assert cfg.embed_dim == 8
    assert cfg.daily_limit == 3


def test_mock_provider_deterministic_and_normalized(monkeypatch):
    monkeypatch.setenv("EMBED_DIM", "16")
    mp = MockProvider(ProviderConfig.from_env())
    v1 = mp.embed(["火锅"])
    v2 = mp.embed(["火锅"])
    assert v1 == v2, "同文本必须同向量（确定性）"
    assert len(v1[0]) == 16
    assert abs(sum(x * x for x in v1[0]) - 1.0) < 1e-6, "向量应归一化（余弦可用）"


def test_daily_limit_enforced(monkeypatch):
    monkeypatch.setenv("LLM_DAILY_LIMIT", "2")
    mp = MockProvider(ProviderConfig.from_env())
    mp.embed(["a"])
    mp.embed(["b"])
    with pytest.raises(DailyLimitError):
        mp.embed(["c"])


def test_make_provider_falls_back_to_mock_without_key(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    mp = __import__("knowledge_rag.provider", fromlist=["make_provider"]).make_provider()
    assert isinstance(mp, MockProvider)


def test_openai_provider_embed_calls_sdk(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("EMBED_DIM", "4")
    cfg = ProviderConfig.from_env()
    p = LLMProvider.__new__(LLMProvider)
    p.config = cfg
    calls = {}

    class FakeEmbeddings:
        def create(self, model, input, dimensions=None):
            calls["model"] = model
            calls["input"] = input
            calls["dimensions"] = dimensions

            class D:
                embedding = [0.25, 0.25, 0.25, 0.25]

            class R:
                data = [D(), D()]

            return R()

    p._client = type("C", (), {"embeddings": FakeEmbeddings()})()
    p.counter = __import__("knowledge_rag.provider", fromlist=["_DailyCounter"])._DailyCounter()

    vecs = p.embed(["hello", "world"])
    assert calls["model"] == cfg.embedding_model
    assert calls["dimensions"] == 4, "必须传 dimensions 使维度与 EMBED_DIM 一致"
    assert len(vecs) == 2 and len(vecs[0]) == 4


def test_sdk_error_translated_to_provider_unavailable(monkeypatch):
    import openai

    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    cfg = ProviderConfig.from_env()
    p = LLMProvider(cfg)

    class FakeEmbeddings:
        def create(self, model, input, dimensions=None):
            raise openai.OpenAIError("404 无此端点（模拟 DeepSeek 无 embeddings）")

    p._client = type("C", (), {"embeddings": FakeEmbeddings()})()
    with pytest.raises(ProviderUnavailableError):
        p.embed(["测试"])
