"""Unit tests for dashboard query compiler."""

from datetime import datetime

import pytest

from apps.shared.core.exceptions import ValidationError
from apps.shared.dashboard.domain import DashboardFilter
from apps.shared.dashboard.query_compiler import compile_query
from apps.shared.domain.value_objects import DataSourceType, resolve_sql_dialect


def test_compile_query_no_filters_with_placeholders_raises():
    with pytest.raises(ValidationError):
        compile_query("SELECT * FROM orders WHERE id = :id", filters=None)


def test_compile_query_no_placeholders_returns_empty_params():
    compiled = compile_query("SELECT * FROM orders", filters=[])

    assert compiled.sql == "SELECT * FROM orders"
    assert compiled.params == {}


def test_time_filter_macro_expands_and_binds_params():
    filters = [
        DashboardFilter(
            id="time_filter",
            name="Time",
            type="time_range",
            param_key="time",
            value={"mode": "relative", "preset": "last_7_days"},
        )
    ]

    compiled = compile_query(
        "SELECT * FROM events WHERE $time_filter(:time, created_at)",
        filters=filters,
    )

    assert "created_at::timestamptz >= :start_time" in compiled.sql
    assert "created_at::timestamptz <= :end_time" in compiled.sql
    assert isinstance(compiled.params["start_time"], datetime)
    assert isinstance(compiled.params["end_time"], datetime)


def test_time_filter_macro_shortcut_uses_single_filter():
    filters = [
        DashboardFilter(
            id="time_filter",
            name="Time",
            type="time_range",
            param_key="time",
            value={"mode": "relative", "preset": "last_7_days"},
        )
    ]

    compiled = compile_query(
        "SELECT * FROM events WHERE $time_filter(created_at)",
        filters=filters,
    )

    assert "created_at::timestamptz >= :start_time" in compiled.sql
    assert "created_at::timestamptz <= :end_time" in compiled.sql
    assert isinstance(compiled.params["start_time"], datetime)
    assert isinstance(compiled.params["end_time"], datetime)


def test_in_or_equal_macro_wraps_single_value():
    filters = [
        DashboardFilter(
            id="status_filter",
            name="Status",
            type="dropdown_static",
            param_key="status",
            value="paid",
        )
    ]

    compiled = compile_query(
        "SELECT * FROM orders WHERE $in_or_equal(:status, status)",
        filters=filters,
    )

    assert (
        "(CASE WHEN CAST(:status AS text[]) IS NULL THEN TRUE ELSE CAST(status AS text) = ANY(CAST(:status AS text[])) END)"
        in compiled.sql
    )
    assert compiled.params["status"] == ["paid"]


def test_in_or_equal_macro_accepts_multiple_values():
    filters = [
        DashboardFilter(
            id="status_filter",
            name="Status",
            type="dropdown_static",
            param_key="status",
            value=["paid", "pending"],
        )
    ]

    compiled = compile_query(
        "SELECT * FROM orders WHERE $in_or_equal(:status, status)",
        filters=filters,
    )

    assert (
        "(CASE WHEN CAST(:status AS text[]) IS NULL THEN TRUE ELSE CAST(status AS text) = ANY(CAST(:status AS text[])) END)"
        in compiled.sql
    )
    assert compiled.params["status"] == ["paid", "pending"]


def test_in_or_equal_macro_casts_values_to_strings():
    filters = [
        DashboardFilter(
            id="tenant_filter",
            name="Tenant",
            type="dropdown_static",
            param_key="tenant_id",
            value=[1, 2],
        )
    ]

    compiled = compile_query(
        "SELECT * FROM orders WHERE $in_or_equal(:tenant_id, tenant_id)",
        filters=filters,
    )

    assert compiled.params["tenant_id"] == ["1", "2"]


def test_in_or_equal_macro_auto_adds_and_after_where_predicate():
    filters = [
        DashboardFilter(
            id="status_filter",
            name="Status",
            type="dropdown_static",
            param_key="status",
            value="paid",
        )
    ]

    compiled = compile_query(
        "SELECT * FROM orders WHERE 1=1 $in_or_equal(:status, status)",
        filters=filters,
    )

    assert (
        "AND (CASE WHEN CAST(:status AS text[]) IS NULL THEN TRUE ELSE CAST(status AS text) = ANY(CAST(:status AS text[])) END)"
        in compiled.sql
    )
    assert compiled.params["status"] == ["paid"]


def test_time_filter_macro_auto_adds_and_after_where_predicate():
    filters = [
        DashboardFilter(
            id="time_filter",
            name="Time",
            type="time_range",
            param_key="time",
            value={"mode": "relative", "preset": "last_7_days"},
        )
    ]

    compiled = compile_query(
        "SELECT * FROM events WHERE 1=1 $time_filter(:time, created_at)",
        filters=filters,
    )

    assert "AND (created_at::timestamptz >= :start_time AND created_at::timestamptz <= :end_time)" in compiled.sql


def test_unknown_placeholder_raises():
    filters = [
        DashboardFilter(
            id="status_filter",
            name="Status",
            type="dropdown_static",
            param_key="status",
            value="paid",
        )
    ]

    with pytest.raises(ValidationError):
        compile_query("SELECT * FROM orders WHERE name = :name", filters=filters)


def test_time_range_legacy_suffix_placeholders_are_bound():
    filters = [
        DashboardFilter(
            id="upload_date_filter",
            name="Upload Date",
            type="time_range",
            param_key="upload_date",
            value={"mode": "relative", "preset": "last_7_days"},
        )
    ]

    compiled = compile_query(
        "SELECT * FROM documents WHERE created_at BETWEEN :upload_date_start AND :upload_date_end",
        filters=filters,
    )

    assert isinstance(compiled.params["upload_date_start"], datetime)
    assert isinstance(compiled.params["upload_date_end"], datetime)


def test_time_range_prefix_and_suffix_placeholders_can_coexist():
    filters = [
        DashboardFilter(
            id="time_filter",
            name="Time",
            type="time_range",
            param_key="time",
            value={"mode": "relative", "preset": "last_7_days"},
        )
    ]

    compiled = compile_query(
        "SELECT * FROM events WHERE created_at >= :start_time AND created_at <= :time_end",
        filters=filters,
    )

    assert isinstance(compiled.params["start_time"], datetime)
    assert isinstance(compiled.params["time_end"], datetime)


def test_time_filter_macro_uses_databricks_timestamp_cast():
    filters = [
        DashboardFilter(
            id="time_filter",
            name="Time",
            type="time_range",
            param_key="time",
            value={"mode": "relative", "preset": "last_7_days"},
        )
    ]

    compiled = compile_query(
        "SELECT * FROM events WHERE $time_filter(:time, created_at)",
        filters=filters,
        dialect=DataSourceType.DATABRICKS,
    )

    assert "CAST(created_at AS TIMESTAMP) >= :start_time" in compiled.sql
    assert "CAST(created_at AS TIMESTAMP) <= :end_time" in compiled.sql


def test_in_or_equal_macro_uses_databricks_in_syntax():
    filters = [
        DashboardFilter(
            id="status_filter",
            name="Status",
            type="dropdown_static",
            param_key="status",
            value=["paid", "pending"],
        )
    ]

    compiled = compile_query(
        "SELECT * FROM orders WHERE $in_or_equal(:status, status)",
        filters=filters,
        dialect=DataSourceType.DATABRICKS,
    )

    assert "(CAST(status AS STRING) IN ('paid', 'pending'))" in compiled.sql
    assert "status" not in compiled.params


def test_in_or_equal_macro_databricks_empty_value_is_true():
    filters = [
        DashboardFilter(
            id="status_filter",
            name="Status",
            type="dropdown_static",
            param_key="status",
            value=None,
        )
    ]

    compiled = compile_query(
        "SELECT * FROM orders WHERE $in_or_equal(:status, status)",
        filters=filters,
        dialect=DataSourceType.DATABRICKS,
    )

    assert "WHERE TRUE" in compiled.sql
    assert compiled.params == {}


def test_databricks_in_or_equal_multi_value_compiles_literals():
    filters = [
        DashboardFilter(
            id="filter-channel",
            name="Channel",
            type="dropdown_static",
            param_key="channel_category",
            value=None,
        ),
        DashboardFilter(
            id="filter-region",
            name="Region",
            type="dropdown_static",
            param_key="region",
            value=["APAC", "EMEA & SEA"],
        ),
    ]

    compiled = compile_query(
        "SELECT * FROM orders WHERE $in_or_equal(:channel_category, channel_category) $in_or_equal(:region, region)",
        filters=filters,
        dialect=DataSourceType.DATABRICKS,
    )

    assert "TRUE" in compiled.sql
    assert "IN ('APAC', 'EMEA & SEA')" in compiled.sql
    assert "IS NULL" not in compiled.sql
    assert compiled.params == {}


def test_databricks_in_or_equal_escapes_quotes():
    filters = [
        DashboardFilter(
            id="status_filter",
            name="Status",
            type="dropdown_static",
            param_key="status",
            value="O'Reilly",
        )
    ]

    compiled = compile_query(
        "SELECT * FROM orders WHERE $in_or_equal(:status, status)",
        filters=filters,
        dialect=DataSourceType.DATABRICKS,
    )

    assert "IN ('O''Reilly')" in compiled.sql


BIND_DIALECTS = (None, "postgres", "mysql", "sqlite", "duckdb", "snowflake", "bigquery")
ALL_DIALECTS = (*BIND_DIALECTS, DataSourceType.DATABRICKS)

POSTGRES_IN_OR_EQUAL = (
    "(CASE WHEN CAST(:status AS text[]) IS NULL THEN TRUE "
    "ELSE CAST(status AS text) = ANY(CAST(:status AS text[])) END)"
)


def _dropdown(
    *,
    param_key: str = "status",
    value: object = "paid",
    filter_type: str = "dropdown_static",
    required: bool = False,
    filter_id: str | None = None,
) -> DashboardFilter:
    return DashboardFilter(
        id=filter_id or f"filter-{param_key}",
        name=param_key,
        type=filter_type,
        param_key=param_key,
        value=value,
        required=required,
    )


def _time_filter(*, param_key: str = "time", value: object | None = None) -> DashboardFilter:
    return DashboardFilter(
        id=f"filter-{param_key}",
        name="Time",
        type="time_range",
        param_key=param_key,
        value=value or {"mode": "relative", "preset": "last_7_days"},
    )


@pytest.mark.parametrize("dialect", BIND_DIALECTS)
def test_bind_dialects_use_postgres_array_in_or_equal(dialect):
    compiled = compile_query(
        "SELECT * FROM orders WHERE $in_or_equal(:status, status)",
        filters=[_dropdown(value=["paid", "pending"])],
        dialect=dialect,
    )

    assert POSTGRES_IN_OR_EQUAL in compiled.sql
    assert compiled.params["status"] == ["paid", "pending"]


@pytest.mark.parametrize("dialect", BIND_DIALECTS)
def test_bind_dialects_use_timestamptz_time_filter(dialect):
    compiled = compile_query(
        "SELECT * FROM events WHERE $time_filter(:time, created_at)",
        filters=[_time_filter()],
        dialect=dialect,
    )

    assert "created_at::timestamptz >= :start_time" in compiled.sql
    assert "created_at::timestamptz <= :end_time" in compiled.sql
    assert isinstance(compiled.params["start_time"], datetime)
    assert isinstance(compiled.params["end_time"], datetime)


@pytest.mark.parametrize("dialect", BIND_DIALECTS)
def test_bind_dialects_empty_in_or_equal_binds_null_array(dialect):
    compiled = compile_query(
        "SELECT * FROM orders WHERE $in_or_equal(:status, status)",
        filters=[_dropdown(value=None)],
        dialect=dialect,
    )

    assert POSTGRES_IN_OR_EQUAL in compiled.sql
    assert compiled.params["status"] is None


@pytest.mark.parametrize("dialect", BIND_DIALECTS)
def test_bind_dialects_required_empty_in_or_equal_raises(dialect):
    with pytest.raises(ValidationError, match="required"):
        compile_query(
            "SELECT * FROM orders WHERE $in_or_equal(:status, status)",
            filters=[_dropdown(value=None, required=True)],
            dialect=dialect,
        )


@pytest.mark.parametrize("dialect", ALL_DIALECTS)
def test_all_dialects_compile_supported_data_source_types(dialect):
    compiled = compile_query(
        "SELECT * FROM orders WHERE $in_or_equal(:status, status) AND $time_filter(:time, created_at)",
        filters=[_dropdown(value="paid"), _time_filter()],
        dialect=dialect,
    )
    assert compiled.sql
    if dialect == DataSourceType.DATABRICKS:
        assert "IN ('paid')" in compiled.sql
        assert "CAST(created_at AS TIMESTAMP)" in compiled.sql
        assert "status" not in compiled.params
        assert "start_time" in compiled.params
    else:
        assert POSTGRES_IN_OR_EQUAL in compiled.sql
        assert "created_at::timestamptz" in compiled.sql
        assert compiled.params["status"] == ["paid"]


@pytest.mark.parametrize("value", [None, "", [], ()])
def test_normalize_empty_in_or_equal_values_match_all(value):
    postgres = compile_query(
        "SELECT * FROM orders WHERE $in_or_equal(:status, status)",
        filters=[_dropdown(value=value)],
        dialect="postgres",
    )
    databricks = compile_query(
        "SELECT * FROM orders WHERE $in_or_equal(:status, status)",
        filters=[_dropdown(value=value)],
        dialect=DataSourceType.DATABRICKS,
    )

    assert postgres.params["status"] is None
    assert "WHERE TRUE" in databricks.sql
    assert databricks.params == {}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("paid", ["paid"]),
        (["paid", "pending"], ["paid", "pending"]),
        (("paid", "pending"), ["paid", "pending"]),
        ([1, 2], ["1", "2"]),
    ],
)
def test_normalize_in_or_equal_values_is_engine_independent(value, expected):
    postgres = compile_query(
        "SELECT * FROM orders WHERE $in_or_equal(:status, status)",
        filters=[_dropdown(value=value)],
        dialect="postgres",
    )
    databricks = compile_query(
        "SELECT * FROM orders WHERE $in_or_equal(:status, status)",
        filters=[_dropdown(value=value)],
        dialect=DataSourceType.DATABRICKS,
    )

    assert postgres.params["status"] == expected
    literals = ", ".join("'" + item.replace("'", "''") + "'" for item in expected)
    assert f"IN ({literals})" in databricks.sql


def test_datasource_dropdown_uses_same_in_or_equal_compilation_as_static():
    static = compile_query(
        "SELECT * FROM orders WHERE $in_or_equal(:region, region)",
        filters=[_dropdown(param_key="region", value=["APAC", "EMEA & SEA"], filter_type="dropdown_static")],
        dialect=DataSourceType.DATABRICKS,
    )
    datasource = compile_query(
        "SELECT * FROM orders WHERE $in_or_equal(:region, region)",
        filters=[
            _dropdown(param_key="region", value=["APAC", "EMEA & SEA"], filter_type="dropdown_datasource")
        ],
        dialect=DataSourceType.DATABRICKS,
    )

    assert static.sql == datasource.sql
    assert "IN ('APAC', 'EMEA & SEA')" in static.sql


def test_databricks_required_empty_in_or_equal_raises():
    with pytest.raises(ValidationError, match="required"):
        compile_query(
            "SELECT * FROM orders WHERE $in_or_equal(:status, status)",
            filters=[_dropdown(value=[], required=True)],
            dialect=DataSourceType.DATABRICKS,
        )


def test_databricks_unknown_in_or_equal_param_raises():
    with pytest.raises(ValidationError, match="Unknown template parameters"):
        compile_query(
            "SELECT * FROM orders WHERE $in_or_equal(:missing, status)",
            filters=[_dropdown(param_key="status", value="paid")],
            dialect=DataSourceType.DATABRICKS,
        )


def test_unused_dropdown_filter_does_not_bind_on_either_engine():
    filters = [_dropdown(param_key="status", value="paid"), _dropdown(param_key="region", value="APAC")]
    postgres = compile_query(
        "SELECT * FROM orders WHERE $in_or_equal(:status, status)",
        filters=filters,
        dialect="postgres",
    )
    databricks = compile_query(
        "SELECT * FROM orders WHERE $in_or_equal(:status, status)",
        filters=filters,
        dialect=DataSourceType.DATABRICKS,
    )

    assert "region" not in postgres.params
    assert "region" not in databricks.sql
    assert "IN ('paid')" in databricks.sql


def test_combined_macros_keep_bound_time_params_on_databricks():
    compiled = compile_query(
        "SELECT * FROM orders WHERE $time_filter(:time, created_at) $in_or_equal(:status, status)",
        filters=[_time_filter(), _dropdown(value=["paid", "O'Reilly"])],
        dialect=DataSourceType.DATABRICKS,
    )

    assert "CAST(created_at AS TIMESTAMP) >= :start_time" in compiled.sql
    assert "IN ('paid', 'O''Reilly')" in compiled.sql
    assert "status" not in compiled.params
    assert isinstance(compiled.params["start_time"], datetime)
    assert isinstance(compiled.params["end_time"], datetime)


def test_invalid_time_filter_macro_raises():
    with pytest.raises(ValidationError, match="Invalid \\$time_filter"):
        compile_query(
            "SELECT * FROM events WHERE $time_filter",
            filters=[_time_filter()],
        )


def test_time_filter_without_time_range_filter_raises():
    with pytest.raises(ValidationError, match="no time_range filter"):
        compile_query(
            "SELECT * FROM events WHERE $time_filter(:time, created_at)",
            filters=[_dropdown(value="paid")],
        )


def test_ambiguous_implicit_time_filter_raises():
    with pytest.raises(ValidationError, match="Ambiguous"):
        compile_query(
            "SELECT * FROM events WHERE $time_filter(created_at)",
            filters=[_time_filter(param_key="time"), _time_filter(param_key="other_time")],
        )


def test_explicit_unknown_time_filter_key_raises():
    with pytest.raises(ValidationError, match="Unknown time filter key"):
        compile_query(
            "SELECT * FROM events WHERE $time_filter(:missing, created_at)",
            filters=[_time_filter()],
        )


SUPPORTED_DATA_SOURCE_TYPES = (
    DataSourceType.POSTGRES,
    DataSourceType.MYSQL,
    DataSourceType.SQLITE,
    DataSourceType.DUCKDB,
    DataSourceType.SNOWFLAKE,
    DataSourceType.BIGQUERY,
    DataSourceType.DATABRICKS,
)


@pytest.mark.parametrize("data_source_type", SUPPORTED_DATA_SOURCE_TYPES)
def test_compile_query_accepts_resolved_dialect_for_each_engine(data_source_type):
    dialect = resolve_sql_dialect(data_source_type)
    assert dialect is not None

    compiled = compile_query(
        "SELECT * FROM orders WHERE $in_or_equal(:status, orders.status) AND $time_filter(:time, orders.created_at)",
        filters=[_dropdown(value=["paid", "O'Reilly"]), _time_filter()],
        dialect=dialect,
    )

    if dialect == DataSourceType.DATABRICKS:
        assert "(CAST(orders.status AS STRING) IN ('paid', 'O''Reilly'))" in compiled.sql
        assert "CAST(orders.created_at AS TIMESTAMP) >= :start_time" in compiled.sql
        assert "status" not in compiled.params
        assert "start_time" in compiled.params
        return

    assert POSTGRES_IN_OR_EQUAL.replace("CAST(status AS text)", "CAST(orders.status AS text)") in compiled.sql
    assert "orders.created_at::timestamptz >= :start_time" in compiled.sql
    assert compiled.params["status"] == ["paid", "O'Reilly"]


def test_non_databricks_engines_currently_share_postgres_bind_sql():
    sql = "SELECT * FROM orders WHERE $in_or_equal(:status, status) AND $time_filter(:time, created_at)"
    filters = [_dropdown(value="paid"), _time_filter()]
    compiled_by_engine = {
        engine: compile_query(sql, filters=filters, dialect=resolve_sql_dialect(engine))
        for engine in (
            DataSourceType.POSTGRES,
            DataSourceType.MYSQL,
            DataSourceType.SQLITE,
            DataSourceType.DUCKDB,
            DataSourceType.SNOWFLAKE,
            DataSourceType.BIGQUERY,
        )
    }

    postgres = compiled_by_engine[DataSourceType.POSTGRES]
    for engine, compiled in compiled_by_engine.items():
        assert compiled.sql == postgres.sql, engine
        assert compiled.params["status"] == ["paid"]
        assert isinstance(compiled.params["start_time"], datetime)


@pytest.mark.parametrize(
    "value",
    [
        "EMEA & SEA",
        "O'Reilly",
        "foo'); DROP TABLE orders;--",
        "north\\south",
        "亚太",
    ],
)
def test_databricks_in_or_equal_escapes_engine_sensitive_literals(value):
    compiled = compile_query(
        "SELECT * FROM orders WHERE $in_or_equal(:region, region)",
        filters=[_dropdown(param_key="region", value=value)],
        dialect=DataSourceType.DATABRICKS,
    )

    expected = "'" + value.replace("'", "''") + "'"
    assert f"IN ({expected})" in compiled.sql
    assert ":" not in compiled.sql.split("IN (", 1)[1]
    assert compiled.params == {}


def test_databricks_auto_adds_and_after_where_predicate():
    compiled = compile_query(
        "SELECT * FROM orders WHERE 1=1 $in_or_equal(:status, status) $time_filter(:time, created_at)",
        filters=[_dropdown(value="paid"), _time_filter()],
        dialect=DataSourceType.DATABRICKS,
    )

    assert "WHERE 1=1 AND (CAST(status AS STRING) IN ('paid'))" in compiled.sql
    assert "AND (CAST(created_at AS TIMESTAMP) >= :start_time" in compiled.sql


@pytest.mark.parametrize("dialect", ALL_DIALECTS)
def test_invalid_time_range_value_raises_on_every_engine(dialect):
    with pytest.raises(ValidationError, match="Invalid time range"):
        compile_query(
            "SELECT * FROM events WHERE $time_filter(:time, created_at)",
            filters=[_time_filter(value={"mode": "absolute", "start": None, "end": None})],
            dialect=dialect,
        )


def test_time_filter_param_without_field_raises():
    with pytest.raises(ValidationError, match="field is required"):
        compile_query(
            "SELECT * FROM events WHERE $time_filter(:time)",
            filters=[_time_filter()],
        )


def test_bind_unknown_in_or_equal_param_raises():
    with pytest.raises(ValidationError, match="Unknown template parameters"):
        compile_query(
            "SELECT * FROM orders WHERE $in_or_equal(:missing, status)",
            filters=[_dropdown(param_key="status", value="paid")],
            dialect="postgres",
        )
