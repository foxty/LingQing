"""Unit tests for Databricks SQL parameter rendering and asset discovery search."""

from datetime import datetime, timezone

import pytest

# Load data_source before analytics_db so package init does not cycle.
import apps.shared.data_source.service  # noqa: F401
from apps.shared.domain.value_objects import DatabaseConnectionVO
from apps.shared.infra.analytics_db.databricks_manager import DatabricksManager


def _manager(*, catalog: str | None = None, schema: str | None = None) -> DatabricksManager:
    extra_params: dict[str, str] = {"warehouse_id": "wh-1"}
    if catalog:
        extra_params["catalog"] = catalog
    if schema:
        extra_params["schema"] = schema
    connection = DatabaseConnectionVO(
        host="adb-1.cloud.databricks.com",
        password="dapi-token",
        extra_params=extra_params,
    )
    return DatabricksManager(tenant_id=1, connection=connection)


def test_render_sql_with_params_handles_null_and_list_values():
    sql = "SELECT * FROM orders WHERE status IN (:status)"
    rendered = DatabricksManager._render_sql_with_params(
        sql,
        {
            "status": ["paid", "pending"],
        },
    )

    assert rendered == "SELECT * FROM orders WHERE status IN ('paid', 'pending')"


def test_render_sql_with_params_escapes_strings_and_formats_datetime():
    sql = "SELECT * FROM t WHERE name = :name AND created_at >= :start_time"
    rendered = DatabricksManager._render_sql_with_params(
        sql,
        {
            "name": "O'Reilly",
            "start_time": datetime(2026, 3, 15, 12, 30, 45, tzinfo=timezone.utc),
        },
    )

    assert "name = 'O''Reilly'" in rendered
    assert "created_at >= '2026-03-15 12:30:45'" in rendered


def test_render_sql_with_params_empty_list_becomes_null():
    sql = "SELECT * FROM t WHERE id IN (:ids)"
    rendered = DatabricksManager._render_sql_with_params(sql, {"ids": []})

    assert "id IN (NULL)" in rendered


def test_extract_column_names_from_result_schema():
    response = {
        "result": {
            "schema": {
                "columns": [
                    {"name": "status", "type_text": "STRING"},
                    {"name": "tag_count", "type_text": "BIGINT"},
                ]
            },
            "data_array": [["active", 12]],
        }
    }

    columns = DatabricksManager._extract_column_names(response)

    assert columns == ["status", "tag_count"]


def test_extract_column_names_from_manifest_schema_fallback():
    response = {
        "manifest": {
            "schema": {
                "columns": [
                    {"name": "k"},
                    {"name": "v"},
                ]
            }
        },
        "result": {"data_array": [["a", 1]]},
    }

    columns = DatabricksManager._extract_column_names(response)

    assert columns == ["k", "v"]


def test_discovery_match_clause_rejects_short_queries():
    assert DatabricksManager._discovery_match_clause(None) is None
    assert DatabricksManager._discovery_match_clause("") is None
    assert DatabricksManager._discovery_match_clause("a") is None
    assert DatabricksManager._discovery_match_clause("  x ") is None


def test_discovery_match_clause_plain_token_uses_bang_escape():
    clause = DatabricksManager._discovery_match_clause("ssot")

    assert clause is not None
    assert "LOWER(table_name) LIKE '%ssot%' ESCAPE '!'" in clause
    assert "\\'" not in clause


def test_discovery_match_clause_single_token_matches_namespace_and_comment():
    clause = DatabricksManager._discovery_match_clause("O'Reilly_100%")

    assert clause is not None
    assert " OR " in clause
    assert "\\'" not in clause
    for expression in ("table_catalog", "table_schema", "table_name", "COALESCE(comment, '')"):
        assert f"LOWER({expression}) LIKE '%o''reilly!_100!%%' ESCAPE '!'" in clause

    backslash_clause = DatabricksManager._discovery_match_clause("a\\nb")
    assert backslash_clause is not None
    assert "LIKE '%a\\\\nb%' ESCAPE '!'" in backslash_clause


def test_discovery_match_clause_dotted_query_binds_parts_in_order():
    two_part = DatabricksManager._discovery_match_clause("main.sales")
    assert two_part is not None
    assert "LOWER(table_catalog) LIKE '%main%' ESCAPE '!'" in two_part
    assert "LOWER(table_schema) LIKE '%sales%' ESCAPE '!'" in two_part
    assert "table_name" not in two_part
    assert "comment" not in two_part

    three_part = DatabricksManager._discovery_match_clause("main.sales.orders")
    assert three_part is not None
    assert "LOWER(table_catalog) LIKE '%main%' ESCAPE '!'" in three_part
    assert "LOWER(table_schema) LIKE '%sales%' ESCAPE '!'" in three_part
    assert "LOWER(table_name) LIKE '%orders%' ESCAPE '!'" in three_part


@pytest.mark.asyncio
async def test_discover_assets_skips_sql_until_query_is_long_enough():
    manager = _manager()

    async def fail_execute(*_args, **_kwargs):
        raise AssertionError("discovery SQL should not run")

    manager._execute_sql = fail_execute  # type: ignore[method-assign]

    for query in (None, "", "a"):
        assets, total = await manager.discover_assets(query=query)
        assert assets == []
        assert total == 0


@pytest.mark.asyncio
async def test_discover_assets_searches_across_namespaces_without_session_scope():
    manager = _manager(catalog="hidden_catalog", schema="hidden_schema")
    calls: list[tuple[str, bool]] = []

    async def fake_execute(statement: str, *, apply_session_namespace: bool = True):
        calls.append((statement, apply_session_namespace))
        if "COUNT(*)" in statement:
            return [[1]]
        return [["main", "finance", "orders", "BASE TABLE", "customer orders"]]

    manager._execute_sql = fake_execute  # type: ignore[method-assign]

    assets, total = await manager.discover_assets(query="orders", include_schema=False)

    assert total == 1
    assert len(assets) == 1
    assert assets[0].name == "main.finance.orders"
    assert calls
    assert all(apply_session_namespace is False for _, apply_session_namespace in calls)
    combined_sql = " ".join(statement for statement, _ in calls)
    assert "hidden_catalog" not in combined_sql
    assert "hidden_schema" not in combined_sql
    assert "table_catalog NOT IN ('system')" in combined_sql
    assert "table_schema NOT IN ('information_schema')" in combined_sql
    assert "LOWER(table_name) LIKE '%orders%' ESCAPE '!'" in combined_sql
