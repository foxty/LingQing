"""Unit tests for shared domain value object helpers."""

import pytest

from apps.shared.domain.value_objects import DatabaseConnectionVO, DataSourceType, resolve_sql_dialect


@pytest.mark.parametrize(
    ("data_source_type", "dialect"),
    [
        (DataSourceType.POSTGRES, "postgres"),
        (DataSourceType.MYSQL, "mysql"),
        (DataSourceType.DATABRICKS, "databricks"),
        (DataSourceType.SQLITE, "sqlite"),
        (DataSourceType.DUCKDB, "duckdb"),
        (DataSourceType.SNOWFLAKE, "snowflake"),
        (DataSourceType.BIGQUERY, "bigquery"),
    ],
)
def test_resolve_sql_dialect_maps_supported_engines(data_source_type, dialect):
    assert resolve_sql_dialect(data_source_type) == dialect


def test_resolve_sql_dialect_unknown_type_returns_none():
    assert resolve_sql_dialect("unknown") is None


def test_databricks_connection_allows_missing_catalog_and_schema():
    connection = DatabaseConnectionVO(
        host="adb-1.cloud.databricks.com",
        password="dapi-token",
        extra_params={"warehouse_id": "wh-1"},
    )

    assert connection.extra_params == {"warehouse_id": "wh-1"}


def test_databricks_connection_still_accepts_optional_catalog_and_schema():
    connection = DatabaseConnectionVO(
        host="adb-1.cloud.databricks.com",
        password="dapi-token",
        extra_params={"warehouse_id": "wh-1", "catalog": "main", "schema": "sales"},
    )

    assert connection.extra_params["catalog"] == "main"
    assert connection.extra_params["schema"] == "sales"


def test_databricks_connection_requires_warehouse_or_http_path():
    with pytest.raises(ValueError, match="warehouse_id"):
        DatabaseConnectionVO(
            host="adb-1.cloud.databricks.com",
            password="dapi-token",
            extra_params={},
        )
