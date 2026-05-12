"""Unit tests for shared domain value object helpers."""

import pytest

from apps.shared.domain.value_objects import DataSourceType, resolve_sql_dialect


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
