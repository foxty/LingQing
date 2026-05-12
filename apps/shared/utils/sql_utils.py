"""Shared SQL utilities: read-only validation and table reference extraction."""

import re

import sqlglot
from sqlglot import expressions as exp
from sqlglot.errors import ParseError

from apps.shared.core.exceptions import ValidationError

_BLOCKED_SQL_PATTERN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|grant|revoke|truncate|merge|call|copy|execute)\b",
    flags=re.IGNORECASE,
)

_SUPPORTED_SQL_DIALECTS: tuple[str | None, ...] = (None, "postgres", "mysql", "databricks")


def strip_sql_comments(sql: str) -> str:
    """Remove block and line comments from a SQL string."""
    without_block = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    without_line = re.sub(r"--.*?$", " ", without_block, flags=re.MULTILINE)
    return without_line


def validate_read_only_sql(sql: str) -> None:
    """Validate that SQL is a read-only SELECT or CTE (WITH) query.

    Strips comments and trailing semicolons before validation.
    Rejects mid-query semicolons (multiple statements), write keywords,
    and anything that is not a SELECT or WITH expression.

    Args:
        sql: Raw SQL string to validate.

    Raises:
        ValidationError: If the SQL is empty, not read-only, or contains
            multiple statements or write operations.
    """
    cleaned = strip_sql_comments(sql).strip().rstrip(";")
    if not cleaned:
        raise ValidationError("SQL query cannot be empty.")

    normalized = " ".join(cleaned.split())
    lowered = normalized.lower()

    if not (lowered.startswith("select") or lowered.startswith("with ")):
        raise ValidationError("Only read-only SELECT queries are allowed.")

    if ";" in normalized:
        raise ValidationError("Only single-statement SQL is allowed.")

    if _BLOCKED_SQL_PATTERN.search(cleaned):
        raise ValidationError("Only read-only SELECT queries are allowed.")


def extract_table_references(sql: str) -> set[str]:
    """Extract table/view names referenced in FROM and JOIN clauses.

    Handles CTEs (WITH expressions) by excluding CTE-defined names from results.
    Strips comments before parsing.

    Args:
        sql: Raw SQL string.

    Returns:
        Set of normalized table reference strings (schema.table or table).
    """
    cleaned = strip_sql_comments(sql)
    tree = _parse_sql_tree(cleaned)

    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE) if cte.alias_or_name}

    table_refs: set[str] = set()
    for table in tree.find_all(exp.Table):
        if not table.name:
            continue

        # Skip CTE references by alias name.
        if table.name.lower() in cte_names:
            continue

        parts = [part for part in (table.catalog, table.db, table.name) if part]
        normalized_ref = ".".join(parts)
        if normalized_ref:
            table_refs.add(normalized_ref)

    return table_refs


def _parse_sql_tree(sql: str):
    """Parse SQL into AST trying supported dialects for cross-engine compatibility."""
    last_error: ParseError | None = None

    for dialect in _SUPPORTED_SQL_DIALECTS:
        try:
            if dialect is None:
                return sqlglot.parse_one(sql)
            return sqlglot.parse_one(sql, read=dialect)
        except ParseError as err:
            last_error = err

    # Should not happen unless all dialect attempts fail.
    if last_error is not None:
        raise last_error
    raise ParseError("Failed to parse SQL.")


def _split_sql_statements_fallback(sql: str) -> list[str]:
    """Split SQL on semicolons outside quotes and PostgreSQL dollar-quoted blocks."""
    statements: list[str] = []
    buf: list[str] = []
    i = 0
    n = len(sql)
    in_single = False
    in_double = False
    dollar_close: str | None = None

    while i < n:
        ch = sql[i]

        if dollar_close is not None:
            if sql.startswith(dollar_close, i):
                buf.extend(dollar_close)
                i += len(dollar_close)
                dollar_close = None
                continue
            buf.append(ch)
            i += 1
            continue

        if in_single:
            buf.append(ch)
            if ch == "'" and i + 1 < n and sql[i + 1] == "'":
                buf.append(sql[i + 1])
                i += 2
                continue
            if ch == "'":
                in_single = False
            i += 1
            continue

        if in_double:
            buf.append(ch)
            if ch == '"' and i + 1 < n and sql[i + 1] == '"':
                buf.append(sql[i + 1])
                i += 2
                continue
            if ch == '"':
                in_double = False
            i += 1
            continue

        if ch == "'" and not in_double:
            in_single = True
            buf.append(ch)
            i += 1
            continue
        if ch == '"' and not in_single:
            in_double = True
            buf.append(ch)
            i += 1
            continue

        if ch == "$":
            j = i + 1
            while j < n and (sql[j].isalnum() or sql[j] == "_"):
                j += 1
            if j < n and sql[j] == "$":
                delim = sql[i : j + 1]
                buf.extend(delim)
                i = j + 1
                dollar_close = delim
                continue

        if ch == "-" and i + 1 < n and sql[i + 1] == "-":
            buf.append(ch)
            buf.append(sql[i + 1])
            i += 2
            while i < n and sql[i] != "\n":
                buf.append(sql[i])
                i += 1
            continue

        if ch == "/" and i + 1 < n and sql[i + 1] == "*":
            buf.append(ch)
            buf.append(sql[i + 1])
            i += 2
            while i + 1 < n and not (sql[i] == "*" and sql[i + 1] == "/"):
                buf.append(sql[i])
                i += 1
            if i + 1 < n:
                buf.append(sql[i])
                buf.append(sql[i + 1])
                i += 2
            continue

        if ch == ";":
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
            i += 1
            continue

        buf.append(ch)
        i += 1

    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


def split_sql_script_statements(sql: str) -> list[str]:
    """Split a PostgreSQL script into statements for drivers that allow one per execute.

    Uses sqlglot when possible; falls back to a lexer-based split on parse failure.
    """
    text = sql.strip()
    if not text:
        return []
    try:
        expressions = sqlglot.parse(text, dialect="postgres")
    except ParseError:
        return _split_sql_statements_fallback(text)
    out: list[str] = []
    for expr in expressions:
        if expr is None:
            continue
        stmt = expr.sql(dialect="postgres").strip()
        if stmt:
            out.append(stmt)
    return out if out else _split_sql_statements_fallback(text)
