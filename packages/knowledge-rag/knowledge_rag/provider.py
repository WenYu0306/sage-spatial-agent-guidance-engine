"""LLM/Embedding Provider 抽象（自建，CLAUDE.md 钦定不引入 LiteLLM）。

OpenAI 兼容 SDK + 环境变量配置；每日调用上限为进程内计数（重启清零，
多进程部署时应在 M5 换 Redis 计数）；tokens 用量记录供成本统计；
降级策略由调用方实现（M6-④ 检索 / M5 编排）。
"""

from __future__ import annotations

import datetime as dt
import hashlib
import math
import os
from dataclasses import dataclass


class DailyLimitError(Exception):
    """当日调用次数超上限（LLM_DAILY_LIMIT）。"""


class ProviderUnavailableError(Exception):
    """Provider 不可用（无 key / 连接失败）——调用方应走降级路径。"""


@dataclass(frozen=True)
class ProviderConfig:
    base_url: str
    api_key: str | None
    chat_model: str
    embedding_model: str
    embed_dim: int
    timeout_s: float
    max_retries: int
    daily_limit: int

    @staticmethod
    def from_env() -> "ProviderConfig":
        return ProviderConfig(
            base_url=os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1"),
            api_key=os.environ.get("LLM_API_KEY") or None,
            chat_model=os.environ.get("LLM_CHAT_MODEL", "gpt-4o-mini"),
            embedding_model=os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small"),
            embed_dim=int(os.environ.get("EMBED_DIM", "1024")),
            timeout_s=float(os.environ.get("LLM_TIMEOUT_S", "30")),
            max_retries=int(os.environ.get("LLM_MAX_RETRIES", "2")),
            daily_limit=int(os.environ.get("LLM_DAILY_LIMIT", "200")),
        )


class _DailyCounter:
    """进程内每日计数：跨日自动清零；超限抛 DailyLimitError。"""

    def __init__(self) -> None:
        self._day = ""
        self._n = 0

    def bump(self, limit: int) -> None:
        today = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d")
        if today != self._day:
            self._day, self._n = today, 0
        self._n += 1
        if self._n > limit:
            raise DailyLimitError(f"每日调用超上限 {limit}")


class MockProvider:
    """无 key / 测试用：sha256 确定性向量（归一化），保证管线可测、无网络依赖。"""

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self.counter = _DailyCounter()

    def embed(self, texts: list[str]) -> list[list[float]]:
        dim = self.config.embed_dim
        out: list[list[float]] = []
        for t in texts:
            self.counter.bump(self.config.daily_limit)
            h = hashlib.sha256(t.encode("utf-8")).digest()
            vec = [h[i % len(h)] / 255.0 for i in range(dim)]
            norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            out.append([x / norm for x in vec])
        return out


class LLMProvider:
    """真实 OpenAI 兼容 Provider；embed 显式传 dimensions 对齐 EMBED_DIM。"""

    def __init__(self, config: ProviderConfig) -> None:
        if not config.api_key:
            raise ProviderUnavailableError("LLM_API_KEY 未设置")
        from openai import OpenAI

        self.config = config
        self.counter = _DailyCounter()
        self._client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout_s,
            max_retries=config.max_retries,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        self.counter.bump(self.config.daily_limit)
        resp = self._client.embeddings.create(
            model=self.config.embedding_model,
            input=texts,
            dimensions=self.config.embed_dim,
        )
        return [d.embedding for d in resp.data]


def make_provider(config: ProviderConfig | None = None):
    """统一入口：有 key 用真实 Provider，否则落 MockProvider（管线可测）。"""
    cfg = config or ProviderConfig.from_env()
    try:
        return LLMProvider(cfg)
    except ProviderUnavailableError:
        return MockProvider(cfg)
