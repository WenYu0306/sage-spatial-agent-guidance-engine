"""Alembic 运行时环境：连接串只从环境变量 DATABASE_URL 读取，禁止硬编码。"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 尚无 ORM metadata（M1 任务引入）；迁移为纯 SQL 风格
target_metadata = None

url = os.environ.get("DATABASE_URL", "")
if not url:
    sys.exit("DATABASE_URL 未设置：复制 .env.example 为 .env 后再运行 make migrate")

# Alembic 用同步驱动
url = url.replace("postgresql+psycopg", "postgresql", 1)


def run_migrations_offline() -> None:
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
