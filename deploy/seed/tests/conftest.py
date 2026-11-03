"""deploy/seed 测试共享夹具：连接 dev Postgres（DATABASE_URL，缺省自动读仓库根 .env）。

数据库不可达时明确失败并提示先 `make compose-up`，不静默跳过。
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_dotenv() -> None:
    """极简 .env 解析（不引入 python-dotenv）：KEY=VALUE、# 注释、setdefault 不覆盖外部环境。"""
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'").strip('"'))


_load_dotenv()


@pytest.fixture(scope="session")
def db_conn():
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL 未设置（复制 .env.example 为 .env）")
    dsn = url.replace("postgresql+psycopg://", "postgresql://", 1)
    try:
        conn = psycopg.connect(dsn)
    except psycopg.OperationalError as exc:
        pytest.fail(f"数据库不可达（先 make compose-up）：{exc}")
    yield conn
    conn.close()
