import pytest

from apps.shared.authz.dsl import (
    AttrRef,
    BinaryExpr,
    DslParseError,
    DslValidationError,
    ListLiteral,
    Literal,
    TermExpr,
    build_attr_registry,
    expr_to_human,
    parse_dsl,
    validate_expr,
)


def test_parse_simple_term():
    expr = parse_dsl(':user.tags has "department:finance"')
    assert isinstance(expr, TermExpr)
    assert expr.left == AttrRef(("user", "tags"))
    assert expr.op == "has"
    assert expr.right == Literal("department:finance")


def test_parse_parentheses_precedence():
    expr = parse_dsl('(:user.id equals :resource.owner_id) or :user.tags has "dept:sales"')
    assert isinstance(expr, BinaryExpr)
    assert expr.op == "or"
    assert isinstance(expr.left, TermExpr)
    assert isinstance(expr.right, TermExpr)


def test_parse_and_or_precedence():
    expr = parse_dsl(':user.tags has "a:b" or :user.tags has "c:d" and :resource.tags has "x:y"')
    assert isinstance(expr, BinaryExpr)
    assert expr.op == "or"
    assert isinstance(expr.right, BinaryExpr)
    assert expr.right.op == "and"


def test_parse_list_literal():
    expr = parse_dsl(':user.id in ("1", "2")')
    assert isinstance(expr, TermExpr)
    assert isinstance(expr.right, ListLiteral)
    assert expr.right.values == ("1", "2")


def test_parse_operator_alias_is_and_unquoted_literal():
    expr = parse_dsl(":user.role is admin")
    assert isinstance(expr, TermExpr)
    assert expr.op == "equals"
    assert expr.right == Literal("admin")


def test_parse_operator_alias_include_and_unquoted_literal():
    expr = parse_dsl(":resource.tags include aabb")
    assert isinstance(expr, TermExpr)
    assert expr.op == "has"
    assert expr.right == Literal("aabb")


def test_parse_errors_on_empty_expression():
    with pytest.raises(DslParseError):
        parse_dsl(" ")


def test_parse_errors_on_missing_paren():
    with pytest.raises(DslParseError):
        parse_dsl('(:user.tags has "dept:sales"')


def test_validate_accepts_supported_attrs():
    registry = build_attr_registry({"resource.owner_id"})
    expr = parse_dsl(":user.id equals :resource.owner_id")
    validate_expr(expr, registry)


def test_validate_rejects_unknown_attr():
    registry = build_attr_registry({"resource.owner_id"})
    expr = parse_dsl(':user.department equals "engineering"')
    with pytest.raises(DslValidationError):
        validate_expr(expr, registry)


def test_validate_rejects_invalid_has_right_operand():
    registry = build_attr_registry({"resource.owner_id"})
    expr = parse_dsl(":user.tags has :resource.tags")
    with pytest.raises(DslValidationError):
        validate_expr(expr, registry)


def test_validate_rejects_invalid_contains_right_operand():
    registry = build_attr_registry({"resource.owner_id"})
    expr = parse_dsl(':user.tags contains "dept:sales"')
    with pytest.raises(DslValidationError):
        validate_expr(expr, registry)


def test_validate_rejects_in_without_list_literal():
    registry = build_attr_registry({"resource.owner_id"})
    expr = parse_dsl(':user.id in "1"')
    with pytest.raises(DslValidationError):
        validate_expr(expr, registry)


def test_parse_contains_with_scoped_keys_parenthesized():
    expr = parse_dsl(':user.tags contains :resource.tags on ("部门", "地区")')
    assert isinstance(expr, TermExpr)
    assert expr.op == "contains"
    assert expr.scope_keys == ("部门", "地区")


def test_parse_contains_with_scoped_keys_shorthand():
    expr = parse_dsl(':user.tags contains :resource.tags on "部门","地区"')
    assert isinstance(expr, TermExpr)
    assert expr.op == "contains"
    assert expr.scope_keys == ("部门", "地区")


def test_validate_accepts_contains_with_scoped_keys_for_user_vs_resource_tags():
    registry = build_attr_registry({"resource.owner_id"})
    expr = parse_dsl(':user.tags contains :resource.tags on ("部门", "地区")')
    validate_expr(expr, registry)


def test_validate_rejects_contains_with_scoped_keys_for_non_supported_attr_pair():
    registry = build_attr_registry({"resource.owner_id"})
    expr = parse_dsl(':resource.tags contains :user.tags on ("部门")')
    with pytest.raises(DslValidationError):
        validate_expr(expr, registry)


# ---------------------------------------------------------------------------
# expr_to_human
# ---------------------------------------------------------------------------


def test_expr_to_human_simple_equals():
    expr = parse_dsl(':user.role equals "admin"')
    assert expr_to_human(expr) == "user.role equals 'admin'"


def test_expr_to_human_has_tag():
    expr = parse_dsl(':user.tags has "dept:sales"')
    assert expr_to_human(expr) == "user.tags has 'dept:sales'"


def test_expr_to_human_in_list():
    expr = parse_dsl(':user.id in ("1","2")')
    assert expr_to_human(expr) == "user.id in ('1', '2')"


def test_expr_to_human_contains():
    expr = parse_dsl(":user.tags contains :resource.tags")
    assert expr_to_human(expr) == "user.tags contains resource.tags"


def test_expr_to_human_contains_with_scoped_keys():
    expr = parse_dsl(':user.tags contains :resource.tags on ("部门", "地区")')
    assert expr_to_human(expr) == "user.tags contains resource.tags on ('部门', '地区')"


def test_expr_to_human_and():
    expr = parse_dsl(':user.role equals "admin" and :user.tags has "dept:sales"')
    result = expr_to_human(expr)
    assert " AND " in result


def test_expr_to_human_nested_or_and():
    # (A and B) or C should produce parens around the "and" group
    expr = parse_dsl('(:user.role equals "admin" and :user.tags has "a:b") or :user.tags has "c:d"')
    result = expr_to_human(expr)
    assert "AND" in result
    assert "OR" in result
    assert result.startswith("(")


def test_user_role_validates_with_default_registry():
    """user.role is now in the default registry; expression must pass validation."""
    registry = build_attr_registry({"resource.owner_id"})
    expr = parse_dsl(':user.role equals "admin"')
    validate_expr(expr, registry)  # must not raise


def test_parse_rank_operator_with_on_key():
    expr = parse_dsl(':user.tags rank_gte :resource.tags on "数据安全性"')
    assert isinstance(expr, TermExpr)
    assert expr.op == "rank_gte"
    assert isinstance(expr.right, AttrRef)
    assert expr.rank_key == "数据安全性"


def test_validate_rank_operator_accepts_user_vs_resource_tags():
    registry = build_attr_registry({"resource.owner_id"})
    expr = parse_dsl(':user.tags rank_gte :resource.tags on "数据安全性"')
    validate_expr(expr, registry)


def test_validate_rank_operator_rejects_missing_on_key():
    with pytest.raises(DslParseError):
        parse_dsl(":user.tags rank_gte :resource.tags")
