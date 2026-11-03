"""US-001 空流程 seed（幂等）：验证数据库连通与表清点，不写入任何业务数据。

真实 demo 数据（虚拟商场）见手册 7.2 任务，届时本脚本升级为"读 YAML 源文件 → 幂等 upsert"。
"""

from __future__ import annotations

import os
import sys

import psycopg


def main() -> int:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("DATABASE_URL 未设置：复制 .env.example 为 .env 后再运行 make seed", file=sys.stderr)
        return 1
    dsn = url.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("select version()")
            print("postgres:", cur.fetchone()[0].split(",")[0])
            cur.execute(
                "select table_name from information_schema.tables "
                "where table_schema = 'public' order by table_name"
            )
            tables = [r[0] for r in cur.fetchall()]
        print(f"public schema 共 {len(tables)} 张表")
        for t in tables:
            with conn.cursor() as cur:
                # 表名来自 information_schema 元数据，非用户输入；仍加引号防保留字
                cur.execute(f'select count(*) from "{t}"')  # noqa: S608
                print(f"  {t}: {cur.fetchone()[0]} 行")
        print("seed 空流程完成（未写入任何数据，天然幂等）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
