"""ABAC policy DSL parsing and validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


class DslParseError(ValueError):
    pass


class DslValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    index: int


@dataclass(frozen=True)
class AttrRef:
    path: tuple[str, ...]

    @property
    def name(self) -> str:
        return ".".join(self.path)


@dataclass(frozen=True)
class Literal:
    value: str


@dataclass(frozen=True)
class ListLiteral:
    values: tuple[str, ...]


ValueExpr = AttrRef | Literal | ListLiteral


@dataclass(frozen=True)
class TermExpr:
    left: AttrRef
    op: str
    right: ValueExpr
    rank_key: str | None = None
    scope_keys: tuple[str, ...] | None = None


@dataclass(frozen=True)
class BinaryExpr:
    op: str
    left: Expr
    right: Expr


Expr = TermExpr | BinaryExpr


KEYWORDS = {
    "and",
    "or",
    "equals",
    "has",
    "contains",
    "in",
    "is",
    "include",
    "includes",
    "on",
    "rank_gte",
    "rank_gt",
    "rank_lte",
    "rank_lt",
    "rank_eq",
}
# rank_* operators compare user/resource tag ranks and require `on "<tag-key>"`.
RANK_OPERATORS = {"rank_gte", "rank_gt", "rank_lte", "rank_lt", "rank_eq"}
OPERATOR_ALIASES = {
    "is": "equals",
    "include": "has",
    "includes": "has",
}


def tokenize(source: str) -> list[Token]:
    """Lex source text into tokens.

    Notes:
    - Bare words become IDENT tokens and may be used as unquoted literals.
    - String literals use double quotes.
    - `:` is tokenized separately so attributes are always parsed as `:segment(.segment)*`.
    """
    tokens: list[Token] = []
    idx = 0
    length = len(source)
    while idx < length:
        char = source[idx]
        if char.isspace():
            idx += 1
            continue
        if char == "(":
            tokens.append(Token("LPAREN", "(", idx))
            idx += 1
            continue
        if char == ")":
            tokens.append(Token("RPAREN", ")", idx))
            idx += 1
            continue
        if char == ":":
            tokens.append(Token("COLON", ":", idx))
            idx += 1
            continue
        if char == ".":
            tokens.append(Token("DOT", ".", idx))
            idx += 1
            continue
        if char == ",":
            tokens.append(Token("COMMA", ",", idx))
            idx += 1
            continue
        if char == '"':
            idx += 1
            start = idx
            while idx < length and source[idx] != '"':
                if source[idx] == "\\" and idx + 1 < length:
                    idx += 2
                    continue
                idx += 1
            if idx >= length:
                raise DslParseError("Unterminated string literal.")
            value = source[start:idx]
            tokens.append(Token("STRING", value, start - 1))
            idx += 1
            continue
        if char.isalpha() or char == "_":
            start = idx
            idx += 1
            while idx < length and (source[idx].isalnum() or source[idx] in {"_", "-"}):
                idx += 1
            value = source[start:idx]
            tokens.append(Token("IDENT", value, start))
            continue
        raise DslParseError(f"Unexpected character at {idx}: {char}")
    return tokens


class Parser:
    """Recursive-descent parser for the ABAC expression grammar.

    Precedence: `and` binds tighter than `or`.
    """

    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.position = 0

    def parse(self) -> Expr:
        if not self.tokens:
            raise DslParseError("Expression cannot be empty.")
        expr = self._parse_or_expr()
        if not self._is_at_end():
            token = self._peek()
            raise DslParseError(f"Unexpected token '{token.value}'.")
        return expr

    def _parse_or_expr(self) -> Expr:
        expr = self._parse_and_expr()
        while self._match_keyword("or"):
            right = self._parse_and_expr()
            expr = BinaryExpr("or", expr, right)
        return expr

    def _parse_and_expr(self) -> Expr:
        expr = self._parse_factor()
        while self._match_keyword("and"):
            right = self._parse_factor()
            expr = BinaryExpr("and", expr, right)
        return expr

    def _parse_factor(self) -> Expr:
        if self._match("LPAREN"):
            expr = self._parse_or_expr()
            if not self._match("RPAREN"):
                raise DslParseError("Missing closing ')'.")
            return expr
        return self._parse_term()

    def _parse_term(self) -> TermExpr:
        left = self._parse_attr()
        op_token = self._consume("IDENT", "Expected operator.")
        op = op_token.value.lower()
        if op not in KEYWORDS:
            raise DslParseError(f"Unsupported operator '{op_token.value}'.")
        op = OPERATOR_ALIASES.get(op, op)

        # rank_* syntax is strict: `:user.tags rank_* :resource.tags on "<key>"`.
        if op in RANK_OPERATORS:
            right = self._parse_attr()
            if not self._match_keyword("on"):
                raise DslParseError("Expected keyword 'on' after rank comparison right operand.")
            rank_key = self._consume("STRING", "Expected rank key string literal after 'on'.").value
            return TermExpr(left=left, op=op, right=right, rank_key=rank_key)

        # Non-rank operators parse normal RHS value first.
        right = self._parse_value()
        scope_keys: tuple[str, ...] | None = None

        # Scoped keys are intentionally strict and currently supported only for
        # `contains` (enforced in validate_expr).
        if op == "contains" and self._match_keyword("on"):
            scope_keys = self._parse_scope_keys()
        return TermExpr(left=left, op=op, right=right, scope_keys=scope_keys)

    def _parse_scope_keys(self) -> tuple[str, ...]:
        # Preferred form: on ("k1", "k2").
        if self._match("LPAREN"):
            keys: list[str] = []
            if not self._check("RPAREN"):
                keys.append(self._consume("STRING", "Expected scope key string literal in list.").value)
                while self._match("COMMA"):
                    keys.append(self._consume("STRING", "Expected scope key string literal in list.").value)
            if not self._match("RPAREN"):
                raise DslParseError("Missing closing ')' for scope keys.")
            if not keys:
                raise DslParseError("Scope key list cannot be empty.")
            return tuple(keys)

        # Backward-compatible shorthand: on "k1","k2".
        keys = [self._consume("STRING", "Expected scope key string literal after 'on'.").value]
        while self._match("COMMA"):
            keys.append(self._consume("STRING", "Expected scope key string literal after ','.").value)
        return tuple(keys)

    def _parse_value(self) -> ValueExpr:
        if self._check("COLON"):
            return self._parse_attr()
        if self._match("STRING"):
            return Literal(self._previous().value)
        if self._match("IDENT"):
            return Literal(self._previous().value)
        if self._match("LPAREN"):
            values = []
            if not self._check("RPAREN"):
                values.append(self._consume("STRING", "Expected string literal in list.").value)
                while self._match("COMMA"):
                    values.append(self._consume("STRING", "Expected string literal in list.").value)
            if not self._match("RPAREN"):
                raise DslParseError("Missing closing ')' for list literal.")
            if not values:
                raise DslParseError("List literal cannot be empty.")
            return ListLiteral(tuple(values))
        token = self._peek()
        raise DslParseError(f"Expected value but found '{token.value}'.")

    def _parse_attr(self) -> AttrRef:
        self._consume("COLON", "Expected ':' before attribute.")
        first = self._consume("IDENT", "Expected attribute name.")
        parts = [first.value]
        while self._match("DOT"):
            part = self._consume("IDENT", "Expected attribute segment.")
            parts.append(part.value)
        return AttrRef(tuple(parts))

    def _match_keyword(self, keyword: str) -> bool:
        if self._check("IDENT") and self._peek().value.lower() == keyword:
            self.position += 1
            return True
        return False

    def _match(self, kind: str) -> bool:
        if self._check(kind):
            self.position += 1
            return True
        return False

    def _check(self, kind: str) -> bool:
        if self._is_at_end():
            return False
        return self._peek().kind == kind

    def _consume(self, kind: str, message: str) -> Token:
        if self._check(kind):
            return self._advance()
        token = self._peek() if not self._is_at_end() else None
        token_value = token.value if token else "<end>"
        raise DslParseError(f"{message} Found '{token_value}'.")

    def _advance(self) -> Token:
        token = self.tokens[self.position]
        self.position += 1
        return token

    def _peek(self) -> Token:
        return self.tokens[self.position]

    def _previous(self) -> Token:
        return self.tokens[self.position - 1]

    def _is_at_end(self) -> bool:
        return self.position >= len(self.tokens)


def parse_dsl(source: str) -> Expr:
    tokens = tokenize(source)
    return Parser(tokens).parse()


@dataclass(frozen=True)
class AttrSpec:
    name: str
    kind: str


def build_attr_registry(resource_attr_names: Iterable[str]) -> dict[str, AttrSpec]:
    registry = {
        "user.id": AttrSpec(name="user.id", kind="scalar"),
        "user.role": AttrSpec(name="user.role", kind="scalar"),
        "user.tags": AttrSpec(name="user.tags", kind="set"),
        "resource.tags": AttrSpec(name="resource.tags", kind="set"),
    }
    for name in resource_attr_names:
        registry[name] = AttrSpec(name=name, kind="scalar")
    return registry


def validate_expr(expr: Expr, registry: dict[str, AttrSpec]) -> None:
    """Type-check and constrain parsed expressions.

    Validation covers:
    - Attribute existence and scalar/set operand compatibility.
    - Operator-specific shape constraints.
    - Strict feature boundaries (e.g. scoped `contains`, rank_* forms).
    """
    errors: list[str] = []

    def check_attr(attr: AttrRef) -> AttrSpec | None:
        spec = registry.get(attr.name)
        if not spec:
            errors.append(f"Unknown attribute '{attr.name}'.")
            return None
        return spec

    def check_term(term: TermExpr) -> None:
        left_spec = check_attr(term.left)
        if not left_spec:
            return
        right_spec: AttrSpec | None = None
        if isinstance(term.right, AttrRef):
            right_spec = check_attr(term.right)
            if not right_spec:
                return

        op = term.op
        if op == "equals":
            if left_spec.kind != "scalar":
                errors.append("equals requires scalar left operand.")
            if isinstance(term.right, AttrRef) and right_spec and right_spec.kind != "scalar":
                errors.append("equals requires scalar right operand.")
            if isinstance(term.right, ListLiteral):
                errors.append("equals does not support list literals.")
        elif op == "has":
            if left_spec.kind != "set":
                errors.append("has requires set left operand.")
            if not isinstance(term.right, Literal):
                errors.append("has requires literal right operand.")
        elif op == "contains":
            if left_spec.kind != "set":
                errors.append("contains requires set left operand.")
            if not isinstance(term.right, AttrRef) or not right_spec or right_spec.kind != "set":
                errors.append("contains requires set right operand.")
            # Strict grammar rule: scoped `on (...)` is allowed only for
            # `:user.tags contains :resource.tags`.
            if term.scope_keys and (
                term.left.name != "user.tags"
                or not isinstance(term.right, AttrRef)
                or term.right.name != "resource.tags"
            ):
                errors.append("contains with scope keys currently supports only ':user.tags contains :resource.tags'.")
        elif op == "in":
            if left_spec.kind != "scalar":
                errors.append("in requires scalar left operand.")
            if not isinstance(term.right, ListLiteral):
                errors.append("in requires list literal right operand.")
        elif op in RANK_OPERATORS:
            if left_spec.kind != "set":
                errors.append(f"{op} requires set left operand.")
            if not isinstance(term.right, AttrRef):
                errors.append(f"{op} requires attribute right operand.")
            elif right_spec and right_spec.kind != "set":
                errors.append(f"{op} requires set right operand.")
            if (
                term.left.name != "user.tags"
                or not isinstance(term.right, AttrRef)
                or term.right.name != "resource.tags"
            ):
                errors.append(f"{op} currently supports only ':user.tags {op} :resource.tags'.")
            if not term.rank_key:
                errors.append(f"{op} requires rank key declaration via 'on \"<key>\"'.")
        else:
            errors.append(f"Unsupported operator '{op}'.")

    def walk(node: Expr) -> None:
        if isinstance(node, TermExpr):
            check_term(node)
        else:
            walk(node.left)
            walk(node.right)

    walk(expr)

    if errors:
        raise DslValidationError(" ".join(errors))


def expr_to_human(expr: Expr) -> str:
    """Convert a parsed DSL expression to a human-readable string."""
    if isinstance(expr, TermExpr):
        left = expr.left.name
        op = expr.op
        if isinstance(expr.right, Literal):
            right = f"'{expr.right.value}'"
        elif isinstance(expr.right, ListLiteral):
            right = "(" + ", ".join(f"'{v}'" for v in expr.right.values) + ")"
        elif isinstance(expr.right, AttrRef):
            right = expr.right.name
        else:
            right = "?"

        if op == "equals":
            return f"{left} equals {right}"
        elif op == "in":
            return f"{left} in {right}"
        elif op == "has":
            return f"{left} has {right}"
        elif op == "contains":
            if expr.scope_keys:
                keys = ", ".join(f"'{v}'" for v in expr.scope_keys)
                return f"{left} contains {right} on ({keys})"
            return f"{left} contains {right}"
        elif op in RANK_OPERATORS and isinstance(expr.right, AttrRef):
            rank_key = expr.rank_key or ""
            return f"{left} {op} {right} on '{rank_key}'"
        return f"{left} {op} {right}"
    else:
        left_str = expr_to_human(expr.left)
        right_str = expr_to_human(expr.right)
        op = expr.op.upper()
        # Add parens for nested binary expressions
        if isinstance(expr.left, BinaryExpr):
            left_str = f"({left_str})"
        if isinstance(expr.right, BinaryExpr):
            right_str = f"({right_str})"
        return f"{left_str} {op} {right_str}"


def collect_attr_names(expr: Expr) -> Iterable[str]:
    names: list[str] = []

    def walk(node: Expr) -> None:
        if isinstance(node, TermExpr):
            names.append(node.left.name)
            if isinstance(node.right, AttrRef):
                names.append(node.right.name)
        else:
            walk(node.left)
            walk(node.right)

    walk(expr)
    return names
