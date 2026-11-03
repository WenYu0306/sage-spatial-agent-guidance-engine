"""配置加载：全部读环境变量（CLAUDE.md：配置外置，禁止硬编码模型名/密钥/权重）。"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    redis_url: str
    sage_env: str
    route_engine_url: str
    knowledge_rag_url: str

    @classmethod
    def from_env(cls) -> "Settings":
        url = os.environ.get("DATABASE_URL", "")
        if not url:
            raise RuntimeError("DATABASE_URL 未设置：复制 .env.example 为 .env")
        return cls(
            database_url=url.replace("postgresql+psycopg://", "postgresql://", 1),
            redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            sage_env=os.environ.get("SAGE_ENV", "dev"),
            route_engine_url=os.environ.get("SVC_ROUTE_ENGINE", "http://localhost:8942"),
            knowledge_rag_url=os.environ.get("SVC_KNOWLEDGE_RAG", "http://localhost:8943"),
        )
