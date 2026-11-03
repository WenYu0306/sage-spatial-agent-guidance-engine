"""demo 数据 seed（幂等）：读 deploy/seed/data/*.yaml → 自然键 upsert → 打印各表行数。

幂等定义：同一数据源连续执行两遍，各表行数不变（首遍 INSERT，后续 UPDATE，不删不重灌）。
演示账号口令从 SEED_DEMO_ADMIN_PASSWORD 读取（bcrypt cost 12）；已存在账号不覆写口令。
数据源 YAML 全部虚构；禁止真实商场/商户/促销信息（手册 7.2 要求 1）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import bcrypt
import psycopg
import yaml
from psycopg.types.json import Jsonb

SEED_DIR = Path(__file__).resolve().parent
DATA_DIR = SEED_DIR / "data"

COUNT_TABLES = (
    "tenants", "users", "roles", "venues", "floors", "map_layers",
    "poi_categories", "pois", "activities", "coupons", "knowledge_documents",
)


def _dsn() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("DATABASE_URL 未设置：复制 .env.example 为 .env 后再运行 make seed", file=sys.stderr)
        raise SystemExit(1)
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def _load_yaml(name: str) -> dict | None:
    path = DATA_DIR / name
    if not path.exists():
        print(f"  [skip] data/{name} 不存在（按子任务计划补齐）")
        return None
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _one(cur, sql: str, params: tuple) -> int | None:
    cur.execute(sql, params)
    row = cur.fetchone()
    return row[0] if row else None


def _seed_identity(cur, data: dict) -> int:
    """租户 + 角色字典 + 演示运营账号。返回 tenant_id。"""
    t = data["tenant"]
    tid = _one(cur, "select id from tenants where code = %s", (t["code"],))
    if tid:
        cur.execute(
            "update tenants set name=%s, plan=%s, status=%s, settings=%s where id=%s",
            (t["name"], t.get("plan", "demo"), t.get("status", "active"),
             Jsonb(t.get("settings", {})), tid),
        )
    else:
        tid = _one(
            cur,
            "insert into tenants (name, code, plan, status, settings) "
            "values (%s, %s, %s, %s, %s) returning id",
            (t["name"], t["code"], t.get("plan", "demo"), t.get("status", "active"),
             Jsonb(t.get("settings", {}))),
        )
    for code in data.get("roles", []):
        cur.execute("insert into roles (code) values (%s) on conflict (code) do nothing", (code,))

    admin = data.get("demo_admin")
    if not admin:
        return tid
    password = os.environ.get("SEED_DEMO_ADMIN_PASSWORD", "")
    if not password:
        print(
            "SEED_DEMO_ADMIN_PASSWORD 未设置：跳过演示账号（补环境变量后重跑即建）",
            file=sys.stderr,
        )
        return tid
    uid = _one(cur, "select id from users where tenant_id = %s and username = %s",
               (tid, admin["username"]))
    if uid:
        # 已存在只更新展示名与状态，永不覆写口令（重复 seed 不搅乱口令）
        cur.execute(
            "update users set display_name=%s, status=%s where id=%s",
            (admin["display_name"], admin.get("status", "active"), uid),
        )
    else:
        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode()
        cur.execute(
            "insert into users (tenant_id, username, password_hash, display_name, status) "
            "values (%s, %s, %s, %s, %s)",
            (tid, admin["username"], hashed, admin["display_name"], admin.get("status", "active")),
        )
    return tid


def _seed_venue(cur, tenant_id: int, data: dict) -> tuple[int, dict[str, int]]:
    """场馆 + 楼层 + 占位底图层。返回 (venue_id, 楼层名→id 映射，供 ③ POI 定位)。"""
    v = data["venue"]
    vid = _one(cur, "select id from venues where tenant_id = %s and name = %s",
               (tenant_id, v["name"]))
    if vid:
        cur.execute(
            "update venues set venue_type=%s, address=%s, timezone=%s, settings=%s, status=%s "
            "where id=%s",
            (v.get("venue_type", "mall"), v.get("address"), v.get("timezone", "Asia/Shanghai"),
              Jsonb(v.get("settings", {})), v.get("status", "active"), vid),
        )
    else:
        vid = _one(
            cur,
            "insert into venues (tenant_id, name, venue_type, address, timezone, settings, status) "
            "values (%s, %s, %s, %s, %s, %s, %s) returning id",
            (tenant_id, v["name"], v.get("venue_type", "mall"), v.get("address"),
             v.get("timezone", "Asia/Shanghai"), Jsonb(v.get("settings", {})),
             v.get("status", "active")),
        )

    for fl in data["floors"]:
        cur.execute(
            "insert into floors (tenant_id, venue_id, name, level, elevation, "
            "is_default, sort_order) "
            "values (%s, %s, %s, %s, %s, %s, %s) "
            "on conflict (venue_id, level) do update set "
            "name=excluded.name, elevation=excluded.elevation, "
            "is_default=excluded.is_default, sort_order=excluded.sort_order",
            (tenant_id, vid, fl["name"], fl["level"], fl.get("elevation", 0),
             bool(fl.get("is_default")), fl.get("sort_order", 0)),
        )

    with cur.connection.cursor() as cur2:
        cur2.execute("select name, id from floors where venue_id = %s", (vid,))
        floor_ids = dict(cur2.fetchall())
    assert len(floor_ids) == len(data["floors"]), "楼层 upsert 后数量与源不符"

    for floor_name, layer in data.get("map_layers", {}).items():
        cur.execute(
            "insert into map_layers (tenant_id, venue_id, floor_id, svg_url, width, height, "
            "scale_meter, version, status) values (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "on conflict (floor_id, version) do update set "
            "svg_url=excluded.svg_url, width=excluded.width, height=excluded.height, "
            "scale_meter=excluded.scale_meter, status=excluded.status",
            (tenant_id, vid, floor_ids[floor_name], layer["svg_url"], layer["width"],
             layer["height"], layer["scale_meter"], layer.get("version", 1),
             layer.get("status", "published")),
        )
    return vid, floor_ids


def _seed_categories(cur, tenant_id: int, tenant_code: str, data: dict) -> None:
    """业态分类字典（数据字典：换场景只改这张表，PRD 6.2）。"""
    src_code = data.get("tenant_code")
    if src_code and src_code != tenant_code:
        raise SystemExit(
            f"poi_categories.yaml 的 tenant_code={src_code} 与租户 {tenant_code} 不一致"
        )
    for c in data["categories"]:
        cur.execute(
            "insert into poi_categories (tenant_id, venue_type, code, name, parent_code, icon, "
            "is_facility, searchable_by_ai, sort_order) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "on conflict (tenant_id, venue_type, code) do update set "
            "name=excluded.name, parent_code=excluded.parent_code, icon=excluded.icon, "
            "is_facility=excluded.is_facility, searchable_by_ai=excluded.searchable_by_ai, "
            "sort_order=excluded.sort_order",
            (tenant_id, data.get("venue_type", "mall"), c["code"], c["name"],
             c.get("parent_code"), c.get("icon"), bool(c.get("is_facility")),
             bool(c.get("searchable_by_ai", True)), c.get("sort_order", 0)),
        )


def _seed_pois(cur, tenant_id: int, venue_id: int, floor_ids: dict[str, int], data: dict) -> None:
    """店铺/设施 upsert（pois 表无唯一约束，按 tenant+venue+floor+name 查改插）。

    YAML 的 hours 是 "HH:MM-HH:MM" 字符串，展开为 PRD 要求的 7 天 JSONB：
    {"mon": [...], ..., "sun": [...], "holidays": []}。
    """
    default_floor = data.get("floor")
    for p in data["pois"]:
        floor = p.get("floor", default_floor)
        fid = floor_ids[floor]
        h = str(p["hours"])
        bh = {**{d: [h] for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")},
              "holidays": []}
        pid = _one(
            cur,
            "select id from pois where tenant_id=%s and venue_id=%s and floor_id=%s and name=%s",
            (tenant_id, venue_id, fid, p["name"]),
        )
        if pid:
            cur.execute(
                "update pois set category_code=%s, intro=%s, contact=%s, position_x=%s, "
                "position_y=%s, business_hours=%s, tags=%s, hot_score=%s, recommend_weight=%s, "
                "status='published', deleted_at=null where id=%s",
                (p["category"], p.get("intro"), p.get("contact", "内线 8000"),
                 float(p["x"]), float(p["y"]), Jsonb(bh), Jsonb(p.get("tags", [])),
                 float(p.get("hot", 0)), float(p.get("weight", 1.0)), pid),
            )
        else:
            cur.execute(
                "insert into pois (tenant_id, venue_id, floor_id, category_code, name, intro, "
                "contact, position_x, position_y, business_hours, tags, hot_score, "
                "recommend_weight, status, published_at) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'published', now())",
                (tenant_id, venue_id, fid, p["category"], p["name"], p.get("intro"),
                 p.get("contact", "内线 8000"), float(p["x"]), float(p["y"]), Jsonb(bh),
                 Jsonb(p.get("tags", [])), float(p.get("hot", 0)),
                 float(p.get("weight", 1.0))),
            )


def run_seed(dsn: str | None = None) -> dict[str, int]:
    """执行完整 seed，返回各表行数（供测试断言幂等与规模）。"""
    with psycopg.connect(dsn or _dsn()) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                tv = _load_yaml("tenant_venue.yaml")
                if tv is None:
                    raise SystemExit("data/tenant_venue.yaml 缺失：它是其余数据组的外键源头")
                tenant_id = _seed_identity(cur, tv)
                venue_id, floor_ids = _seed_venue(cur, tenant_id, tv)
                cats = _load_yaml("poi_categories.yaml")
                if cats:
                    _seed_categories(cur, tenant_id, tv["tenant"]["code"], cats)
                pois_files = (
                    "pois_b1.yaml", "pois_f1.yaml", "pois_f2.yaml", "facilities.yaml",
                )
                for pois_file in pois_files:
                    d = _load_yaml(pois_file)
                    if d:
                        _seed_pois(cur, tenant_id, venue_id, floor_ids, d)
# ③④⑤ 在此追加：pois/facilities → activities/coupons → knowledge/eval 基线
    return count_rows(dsn or _dsn())


def count_rows(dsn: str | None = None) -> dict[str, int]:
    dsn = dsn or _dsn()
    counts: dict[str, int] = {}
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            for t in COUNT_TABLES:
                cur.execute(f'select count(*) from "{t}"')  # noqa: S608 表名来自常量白名单
                counts[t] = cur.fetchone()[0]
    return counts


def main() -> int:
    print("== demo seed 开始（数据源：deploy/seed/data）==")
    counts = run_seed()
    print("== seed 完成，各表行数 ==")
    for table, n in counts.items():
        print(f"  {table}: {n} 行")
    print("幂等性：首遍 INSERT，后续 UPDATE；连续执行行数不变（deploy/seed/tests 已断言）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
