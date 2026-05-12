import pytest

from apps.shared.utils.sql_utils import extract_table_references, split_sql_script_statements


def test_extract_table_references_basic_select():
    refs = extract_table_references("SELECT * FROM orders")

    assert refs == {"orders"}


def test_extract_table_references_ignores_function_from_expression_token():
    refs = extract_table_references(
        "WITH product_sales_2015 AS ( "
        "SELECT primary_product_id, SUM(items_purchased) as total_sales "
        "FROM orders "
        "WHERE EXTRACT(YEAR FROM created_at::timestamp) = 2015 "
        "GROUP BY primary_product_id "
        ") "
        "SELECT primary_product_id, total_sales FROM product_sales_2015"
    )

    assert refs == {"orders"}


def test_extract_table_references_excludes_cte_alias_name():
    refs = extract_table_references("WITH scoped AS (SELECT * FROM orders) SELECT * FROM scoped")

    assert refs == {"orders"}


@pytest.mark.parametrize(
    ("sql", "expected_refs"),
    [
        (
            "SELECT o.id, c.name FROM sales.orders o JOIN sales.customers c ON o.customer_id = c.id",
            {"sales.orders", "sales.customers"},
        ),
        (
            "SELECT * FROM (SELECT * FROM orders) sub JOIN customers c ON sub.customer_id = c.id",
            {"orders", "customers"},
        ),
        (
            "-- comment\nSELECT * FROM orders o /* inline */ JOIN products p ON o.product_id = p.id",
            {"orders", "products"},
        ),
    ],
)
def test_extract_table_references_various_sql_patterns(sql: str, expected_refs: set[str]):
    assert extract_table_references(sql) == expected_refs


@pytest.mark.parametrize(
    ("sql", "expected_refs"),
    [
        # Postgres: cast and schema-qualified references.
        (
            "SELECT * FROM public.orders WHERE EXTRACT(YEAR FROM created_at::timestamp) = 2015",
            {"public.orders"},
        ),
        # MySQL: backtick identifiers and DATE_FORMAT.
        (
            "SELECT DATE_FORMAT(created_at, '%Y-%m') m FROM `shop`.`orders` WHERE `created_at` >= '2024-01-01'",
            {"shop.orders"},
        ),
        # Databricks/Spark SQL: catalog.schema.table style.
        (
            "SELECT * FROM hive_metastore.analytics.orders WHERE order_date >= DATE('2024-01-01')",
            {"hive_metastore.analytics.orders"},
        ),
    ],
)
def test_extract_table_references_cross_database_dialects(sql: str, expected_refs: set[str]):
    assert extract_table_references(sql) == expected_refs


def test_split_sql_script_statements_multiple_ddl():
    sql = """
    CREATE TABLE tasks (id INT);
    CREATE INDEX idx_tasks_completed ON tasks(completed);
    CREATE INDEX idx_tasks_priority ON tasks(priority);
    """
    parts = split_sql_script_statements(sql)
    assert len(parts) == 3
    assert "CREATE TABLE tasks" in parts[0]
    assert "idx_tasks_completed" in parts[1]
    assert "idx_tasks_priority" in parts[2]


def test_split_sql_script_statements_semicolon_in_string():
    sql = "CREATE TABLE t (a TEXT DEFAULT 'a;b');"
    assert split_sql_script_statements(sql) == [sql.strip().rstrip(";")]


def test_split_sql_script_statements_fallback_dollar_quote():
    sql = r"""
    CREATE OR REPLACE FUNCTION f() RETURNS void AS $fn$
    BEGIN
      PERFORM 1;
    END;
    $fn$ LANGUAGE plpgsql;
    """
    parts = split_sql_script_statements(sql)
    assert len(parts) == 1
    assert "CREATE OR REPLACE FUNCTION f()" in parts[0]
