"""0002 迁移的表结构验收：demo 数据所需的 11 张表与关键列/唯一约束必须存在（PRD 6.1/6.2/6.4/6.5）。

先于 0002 迁移运行时应失败于"缺表"——即 TDD 的红灯。
"""

from __future__ import annotations

import pytest

EXPECTED_TABLES = {
    "tenants", "users", "roles", "venues", "floors", "map_layers",
    "poi_categories", "pois", "activities", "coupons", "knowledge_documents",
    "route_nodes", "route_edges", "knowledge_chunks",
    "agent_sessions", "agent_messages", "agent_traces", "agent_tools", "coupon_claims",
}

# 表 → 关键列抽样（防迁移走样，非全量 DDL 复制）
EXPECTED_COLUMNS = {
    "tenants": {"code", "plan", "settings"},
    "users": {"tenant_id", "username", "password_hash", "failed_logins"},
    "roles": {"code"},
    "venues": {"tenant_id", "venue_type", "timezone", "settings"},
    "floors": {"venue_id", "level", "elevation", "is_default"},
    "map_layers": {"floor_id", "svg_url", "scale_meter", "version"},
    "poi_categories": {"venue_type", "code", "is_facility", "searchable_by_ai"},
    "pois": {
        "category_code", "position_x", "position_y", "business_hours",
        "tags", "hot_score", "recommend_weight", "deleted_at",
    },
    "activities": {"poi_id", "act_type", "start_at", "end_at", "created_by"},
    "coupons": {"coupon_type", "threshold", "value", "total_qty", "per_user_limit"},
    "knowledge_documents": {"poi_id", "doc_type", "content", "version"},
    "route_nodes": {"floor_id", "node_type", "poi_id", "x", "y", "accessible"},
    "route_edges": {"from_node_id", "to_node_id", "edge_type", "distance_meter",
                    "weight", "accessible", "is_bidirectional"},
    "knowledge_chunks": {"document_id", "tenant_id", "venue_id", "chunk_index",
                         "content", "token_count", "embedding"},
    "agent_sessions": {"tenant_id", "venue_id", "device_id", "anonymous_id",
                       "channel", "status", "handed_to_session_id"},
    "agent_messages": {"session_id", "tenant_id", "role", "content", "structured",
                       "tokens_in", "tokens_out"},
    "agent_traces": {"session_id", "message_id", "tenant_id", "trace_id", "step_index",
                     "step_type", "tool_code", "input", "output", "status",
                     "latency_ms", "error_code"},
    "agent_tools": {"code", "name", "description", "input_schema", "output_schema",
                    "endpoint", "timeout_ms", "enabled", "version"},
    "coupon_claims": {"coupon_id", "anonymous_id", "claim_status", "claimed_at",
                      "used_at", "idempotency_key"},
}

# 这些表的唯一约束各只有一个（PRD DDL 如此），按"列并集"比对即可
EXPECTED_UNIQUES = {
    "tenants": {"code"},
    "users": {"tenant_id", "username"},
    "floors": {"venue_id", "level"},
    "map_layers": {"floor_id", "version"},
    "poi_categories": {"tenant_id", "venue_type", "code"},
    "route_edges": {"from_node_id", "to_node_id", "edge_type"},
    "knowledge_chunks": {"document_id", "chunk_index"},
    "agent_tools": {"code"},
    "coupon_claims": {"idempotency_key"},
}


def test_expected_tables_exist(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "select table_name from information_schema.tables where table_schema = 'public'"
        )
        actual = {r[0] for r in cur.fetchall()}
    missing = EXPECTED_TABLES - actual
    assert not missing, f"缺表 {sorted(missing)}：先执行 make migrate"


@pytest.mark.parametrize("table", sorted(EXPECTED_COLUMNS))
def test_key_columns_exist(db_conn, table):
    with db_conn.cursor() as cur:
        cur.execute(
            "select column_name from information_schema.columns "
            "where table_schema = 'public' and table_name = %s",
            (table,),
        )
        actual = {r[0] for r in cur.fetchall()}
    missing = EXPECTED_COLUMNS[table] - actual
    assert not missing, f"{table} 缺列 {sorted(missing)}（对照 PRD 第 6 节 DDL）"


@pytest.mark.parametrize("table", sorted(EXPECTED_UNIQUES))
def test_unique_constraints(db_conn, table):
    with db_conn.cursor() as cur:
        cur.execute(
            "select kcu.column_name from information_schema.table_constraints tc "
            "join information_schema.key_column_usage kcu "
            "  on tc.constraint_name = kcu.constraint_name "
            " and tc.table_schema = kcu.table_schema "
            "where tc.table_schema = 'public' and tc.table_name = %s "
            "  and tc.constraint_type = 'UNIQUE'",
            (table,),
        )
        actual = {r[0] for r in cur.fetchall()}
    assert EXPECTED_UNIQUES[table] <= actual, (
        f"{table} 唯一约束缺失：期望含 {sorted(EXPECTED_UNIQUES[table])}，实际 {sorted(actual)}"
    )


def test_pois_gin_index_on_tags(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "select indexname from pg_indexes "
            "where schemaname = 'public' and tablename = 'pois'"
        )
        indexes = {r[0] for r in cur.fetchall()}
    assert "idx_pois_tags_gin" in indexes, "pois.tags 缺 GIN 索引（AI 标签检索依赖它）"
