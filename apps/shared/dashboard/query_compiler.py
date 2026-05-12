"""Compile dashboard SQL templates with filters into prepared statements."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from apps.shared.core.exceptions import ValidationError
from apps.shared.dashboard.domain import DashboardFilter, TimeRangeResolver
from apps.shared.domain.value_objects import DataSourceType, SQLDialectStr

PARAM_NAME_PATTERN = re.compile(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)")
TIME_FILTER_PATTERN = re.compile(
    r"\$time_filter\(\s*(?::(?P<param>[A-Za-z_][A-Za-z0-9_]*))?\s*(?:,\s*(?P<field>.+?)\s*|(?P<field_only>.+?)\s*)?\)"
)
IN_OR_EQUAL_PATTERN = re.compile(r"\$in_or_equal\(\s*:([A-Za-z_][A-Za-z0-9_]*)\s*,\s*(.+?)\s*\)")
PRECEDING_CONJUNCTION_PATTERN = re.compile(r"(?:\bAND\b|\bOR\b|\bWHERE\b|\()\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class CompiledQuery:
    """Compiled SQL template and bound params."""

    sql: str
    params: dict[str, Any]


def compile_query(
    base_query: str,
    filters: list[DashboardFilter] | None,
    dialect: SQLDialectStr | None = None,
) -> CompiledQuery:
    """Compile SQL with dashboard filters into prepared statement + params."""
    in_or_equal_values = _collect_in_or_equal_values(filters)
    working_query = _expand_time_filter_macros(base_query, filters, dialect=dialect)
    working_query, in_or_equal_params = _expand_in_or_equal_macros(
        working_query,
        dialect=dialect,
        values_by_key=in_or_equal_values,
        filters=filters,
    )

    if not filters:
        if _extract_query_placeholders(working_query):
            raise ValidationError("Query contains template parameters but no filters are configured")
        return CompiledQuery(sql=working_query, params={})

    placeholders = _extract_query_placeholders(working_query)
    if not placeholders:
        return CompiledQuery(sql=working_query, params={})

    expected_params: set[str] = set()
    params: dict[str, Any] = {}

    for dashboard_filter in filters:
        param_keys = _get_filter_param_names(dashboard_filter)
        if not param_keys:
            continue

        expected_params.update(param_keys)
        matched_keys = [key for key in param_keys if key in placeholders]
        if not matched_keys:
            continue

        value = dashboard_filter.value
        is_empty_collection = isinstance(value, (list, tuple, set)) and len(value) == 0
        if value is None or is_empty_collection or value == "":
            if getattr(dashboard_filter, "required", False):
                raise ValidationError(
                    f"Filter '{dashboard_filter.id}' is required but has no value for placeholders {matched_keys}"
                )
            for key in matched_keys:
                params[key] = None
            continue

        if dashboard_filter.type == "time_range":
            # Get precision from filter config, defaults to 'datetime' for backward compatibility
            precision = getattr(dashboard_filter, "time_precision", None) or "datetime"
            resolved = TimeRangeResolver.resolve(value, precision=precision)
            if not resolved:
                raise ValidationError(f"Invalid time range value for filter '{dashboard_filter.id}'")
            start, end = resolved
            for key in matched_keys:
                if key.startswith("start_") or key.endswith("_start"):
                    params[key] = start
                elif key.startswith("end_") or key.endswith("_end"):
                    params[key] = end
        else:
            if matched_keys[0] in in_or_equal_params:
                value = in_or_equal_values.get(matched_keys[0], _normalize_in_or_equal_value(value))
            params[matched_keys[0]] = value

    unknown = placeholders - expected_params
    if unknown:
        raise ValidationError(f"Unknown template parameters: {', '.join(sorted(unknown))}")

    return CompiledQuery(sql=working_query, params=params)


def _maybe_prefix_with_and(query: str, match: re.Match[str], clause: str) -> str:
    prefix = query[: match.start()].rstrip()
    if not prefix:
        return clause
    if PRECEDING_CONJUNCTION_PATTERN.search(prefix) is not None:
        return clause
    return f"AND {clause}"


def _normalize_in_or_equal_value(value: Any) -> list[str] | None:
    """Normalize dropdown / IN values. None means match all rows."""
    if value is None or value == "":
        return None
    if isinstance(value, (list, tuple, set)):
        items = [str(item) for item in value]
        return items or None
    return [str(value)]


def _sql_string_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _collect_in_or_equal_values(filters: list[DashboardFilter] | None) -> dict[str, list[str] | None]:
    values: dict[str, list[str] | None] = {}
    for dashboard_filter in filters or []:
        if dashboard_filter.type == "time_range":
            continue
        param_keys = _get_filter_param_names(dashboard_filter)
        if not param_keys:
            continue
        values[param_keys[0]] = _normalize_in_or_equal_value(dashboard_filter.value)
    return values


def _filter_required_param_keys(filters: list[DashboardFilter] | None) -> set[str]:
    required: set[str] = set()
    for dashboard_filter in filters or []:
        if not getattr(dashboard_filter, "required", False):
            continue
        param_keys = _get_filter_param_names(dashboard_filter)
        required.update(param_keys)
    return required


def _expand_in_or_equal_macros(
    query: str,
    dialect: SQLDialectStr | None = None,
    values_by_key: dict[str, list[str] | None] | None = None,
    filters: list[DashboardFilter] | None = None,
) -> tuple[str, set[str]]:
    if not IN_OR_EQUAL_PATTERN.search(query):
        return query, set()

    param_keys: set[str] = set()
    resolved_values = values_by_key or {}
    required_keys = _filter_required_param_keys(filters)

    def replacer(match: re.Match[str]) -> str:
        param_key = match.group(1)
        field_name = match.group(2)
        param_keys.add(param_key)
        if dialect == DataSourceType.DATABRICKS:
            if param_key not in resolved_values:
                raise ValidationError(f"Unknown template parameters: {param_key}")
            selected = resolved_values[param_key]
            if selected is None:
                if param_key in required_keys:
                    raise ValidationError(
                        f"Filter '{param_key}' is required but has no value for placeholders {param_key}"
                    )
                clause = "TRUE"
            else:
                literals = ", ".join(_sql_string_literal(item) for item in selected)
                clause = f"(CAST({field_name} AS STRING) IN ({literals}))"
        else:
            clause = (
                f"(CASE WHEN CAST(:{param_key} AS text[]) IS NULL THEN TRUE "
                f"ELSE CAST({field_name} AS text) = ANY(CAST(:{param_key} AS text[])) END)"
            )
        return _maybe_prefix_with_and(query, match, clause)

    return IN_OR_EQUAL_PATTERN.sub(replacer, query), param_keys


def _expand_time_filter_macros(
    query: str, filters: list[DashboardFilter] | None, dialect: SQLDialectStr | None = None
) -> str:
    if "$time_filter" in query and not TIME_FILTER_PATTERN.search(query):
        raise ValidationError(
            "Invalid $time_filter usage; expected $time_filter(:param_key, field) or $time_filter(field)"
        )

    if not TIME_FILTER_PATTERN.search(query):
        return query

    if not filters:
        raise ValidationError("Query contains $time_filter but no filters are configured")

    time_filters = [f for f in filters if f.type == "time_range"]
    if not time_filters:
        raise ValidationError("Query contains $time_filter but no time_range filter is configured")

    key_map: dict[str, DashboardFilter] = {}

    for dashboard_filter in time_filters:
        try:
            base_key = dashboard_filter.get_normalized_param_key()
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        key_map[base_key] = dashboard_filter

    def replacer(match: re.Match[str]) -> str:
        param_key = match.group("param")
        explicit_field = match.group("field")
        field_only = match.group("field_only")

        # Determine base_key and column based on syntax
        if param_key and explicit_field:
            # Explicit syntax: $time_filter(:param_key, field)
            if param_key not in key_map:
                raise ValidationError(
                    f"Unknown time filter key '{param_key}' in $time_filter(:{param_key}, {explicit_field})"
                )
            base_key = param_key
            column = explicit_field
        elif param_key and not explicit_field:
            raise ValidationError("Invalid $time_filter usage; field is required when param key is provided")
        elif field_only:
            # Implicit syntax: $time_filter(field) - infer from available filters
            if len(time_filters) == 1:
                dashboard_filter = time_filters[0]
                try:
                    base_key = dashboard_filter.get_normalized_param_key()
                except ValueError as exc:
                    raise ValidationError(str(exc)) from exc
                column = field_only
            else:
                raise ValidationError(
                    f"Ambiguous $time_filter({field_only}); multiple time filters exist. "
                    f"Use explicit syntax: $time_filter(:param_key, {field_only})"
                )
        else:
            raise ValidationError("Invalid $time_filter usage; expected $time_filter(field)")

        if dialect == DataSourceType.DATABRICKS:
            clause = (
                f"(CAST({column} AS TIMESTAMP) >= :start_{base_key} AND CAST({column} AS TIMESTAMP) <= :end_{base_key})"
            )
        else:
            # Handle timezone by casting timestamp column to timestamptz for comparison.
            clause = f"({column}::timestamptz >= :start_{base_key} AND {column}::timestamptz <= :end_{base_key})"

        return _maybe_prefix_with_and(query, match, clause)

    return TIME_FILTER_PATTERN.sub(replacer, query)


def _extract_query_placeholders(query: str) -> set[str]:
    return set(PARAM_NAME_PATTERN.findall(query))


def _normalize_param_key(key: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_]", "_", key)
    if not normalized or normalized[0].isdigit():
        normalized = f"filter_{normalized}"
    return normalized


def _get_filter_param_names(dashboard_filter: DashboardFilter) -> list[str]:
    """Get parameter names for a filter, delegating to the filter's own method."""
    try:
        return dashboard_filter.get_param_names()
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
