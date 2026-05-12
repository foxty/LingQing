"""Unit tests for Databricks SQL parameter rendering."""

from datetime import datetime, timezone

from apps.shared.infra.analytics_db.databricks_manager import DatabricksManager


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
