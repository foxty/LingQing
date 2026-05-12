"""SQL pushdown helpers for ABAC policy enforcement."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from sqlalchemy import and_, false, func, literal, or_, select
from sqlalchemy.sql.elements import ColumnElement

from apps.shared.authz.acl import AclCheckInput, AclDecision, evaluate_acl_action
from apps.shared.authz.dsl import (
    RANK_OPERATORS,
    AttrRef,
    DslParseError,
    DslValidationError,
    Expr,
    ListLiteral,
    Literal,
    TermExpr,
    build_attr_registry,
    parse_dsl,
    validate_expr,
)
from apps.shared.authz.repository import AbacPolicyRepository
from apps.shared.db.models import (
    AbacPolicy,
    AclGrant,
    Agent,
    ApiConnector,
    DataSource,
    Document,
    DocumentCollection,
    ResourceAcl,
    TagBinding,
    TagKey,
    TagValue,
)
from apps.shared.domain.types import (
    ABAC_ACTION_READ,
    RESOURCE_TYPE_AGENT,
    RESOURCE_TYPE_API_CONNECTOR,
    RESOURCE_TYPE_DATA_SOURCE,
    RESOURCE_TYPE_DOCUMENT,
    RESOURCE_TYPE_DOCUMENT_COLLECTION,
    RESOURCE_TYPE_USER,
    ResourceType,
    required_acl_permissions,
    to_abac_action,
)
from apps.shared.tag.repository import TagBindingRepository, TagKeyRepository
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)

SimulationOwnerResolver = Callable[[object, int, int], Awaitable[int | None]]

# Unified ABAC behavior for all callers.
_ABAC_DEFAULT_ALLOW_IF_NO_POLICY = True
_ABAC_STRICT_POLICY_VALIDATION = False


class AbacPolicyCompileError(Exception):
    """Raised when an ABAC policy cannot be safely compiled to SQL."""


@dataclass(frozen=True)
class AuthzSqlFilter:
    allow_all: bool
    deny_all: bool
    clause: ColumnElement[bool] | None


@dataclass(frozen=True)
class ResourceTagContext:
    tags: set[str]
    max_rank_by_key: dict[str, int]


def _build_resource_literal_attr_map(resource_id: int, resource_owner_id: int | None) -> dict[str, ColumnElement]:
    """Build SQL literal-based resource attrs for single-resource evaluation paths."""
    return {
        "resource.id": literal(resource_id),
        "resource.owner_id": literal(resource_owner_id),
    }


async def _build_abac_resource_filter(
    *,
    db_session,
    tenant_id: int,
    user_id: int,
    user_role: str | None = None,
    resource_type: ResourceType,
    action: str = ABAC_ACTION_READ,
    resource_id_column,
    resource_attr_map: dict[str, ColumnElement] | None = None,
) -> AuthzSqlFilter:
    """Build an ABAC-only SQL filter for list/search style pushdown.

    This compiles active ABAC policies into a SQL predicate over the target
    resource table using the provided resource id/attribute columns.

    Args:
        db_session: Async DB session.
        tenant_id: Tenant scope for policy/tag lookups.
        user_id: Current user id used for user tag context.
        user_role: Optional role value for :user.role expressions.
        resource_type: Resource type key used by policy selection.
        action: Requested action; normalized via ``to_abac_action``.
        resource_id_column: SQLAlchemy column/expression for resource id.
        resource_attr_map: Optional mapping for DSL resource attrs,
            e.g. ``{"resource.owner_id": Model.owner_id}``.

    Returns:
        AuthzSqlFilter with one of three states:
        - allow_all=True: caller may skip SQL predicate.
        - deny_all=True: caller should return no rows.
        - clause=<sql expr>: caller applies this predicate in WHERE.
    """
    normalized_action = to_abac_action(action)
    policy_repo = AbacPolicyRepository(db_session)
    tag_binding_repo = TagBindingRepository(db_session)
    tag_key_repo = TagKeyRepository(db_session)

    policies = await policy_repo.list_by_resource_type_and_action(tenant_id, resource_type, normalized_action)
    active_policies = [policy for policy in policies if policy.status == "active"]

    if not active_policies:
        if _ABAC_DEFAULT_ALLOW_IF_NO_POLICY:
            return AuthzSqlFilter(allow_all=True, deny_all=False, clause=None)
        return AuthzSqlFilter(allow_all=False, deny_all=True, clause=None)

    tag_key_map = {tag_key.id: tag_key.name for tag_key in await tag_key_repo.list_by_tenant(tenant_id)}
    user_tag_context = await _get_resource_tag_context(
        tag_binding_repo=tag_binding_repo,
        tenant_id=tenant_id,
        resource_type=RESOURCE_TYPE_USER,
        resource_id=user_id,
        tag_key_map=tag_key_map,
    )

    policy_clauses: list[ColumnElement[bool]] = []
    resolved_resource_attrs = {"resource.id": resource_id_column}
    if resource_attr_map:
        resolved_resource_attrs.update(resource_attr_map)
    for policy in active_policies:
        policy_clause = _build_policy_clause(
            policy,
            user_tag_context,
            tenant_id,
            resource_type,
            resource_id_column,
            resolved_resource_attrs,
            user_id,
            user_role,
        )
        if policy_clause is None:
            continue
        if policy_clause is True:
            return AuthzSqlFilter(allow_all=True, deny_all=False, clause=None)
        policy_clauses.append(policy_clause)

    if not policy_clauses:
        return AuthzSqlFilter(allow_all=False, deny_all=True, clause=None)

    return AuthzSqlFilter(allow_all=False, deny_all=False, clause=or_(*policy_clauses))


async def build_unified_resource_filter(
    *,
    db_session,
    tenant_id: int,
    user_id: int,
    user_role: str | None = None,
    resource_type: ResourceType,
    action: str = ABAC_ACTION_READ,
    resource_model=None,
    resource_id_column=None,
    resource_attr_map: dict[str, ColumnElement] | None = None,
    resource_owner_id_column: ColumnElement | None = None,
    has_manage_permission: bool = False,
) -> AuthzSqlFilter:
    """Build a unified ABAC + ACL SQL filter for list/search pushdown.

    Semantics:
    - ABAC is the baseline policy layer.
    - ACL is supplemental sharing and can only add allows.
    - Final list scope is additive: ``ABAC_ALLOW OR ACL_ALLOW``.
    - ACL presence does not constrain ABAC-allowed access.

    Convention over configuration:
    - Prefer passing ``resource_model`` and let this method resolve columns.
    - ``resource_model.id`` is used as default ``resource_id_column``.
    - ``resource_model.owner_id`` is used as default owner column when present.
    - Explicit ``resource_id_column`` / ``resource_owner_id_column`` still
      override defaults for legacy/non-conventional models.

    Args:
        db_session: Async DB session.
        tenant_id: Tenant scope.
        user_id: Current user id.
        user_role: Optional role id/name for role principal matching.
        resource_type: Resource type key.
        action: Requested action.
        resource_model: Optional SQLAlchemy model following ``id`` and
            ``owner_id`` conventions.
        resource_id_column: Optional explicit resource id column.
        resource_attr_map: Optional ABAC resource attribute map.
        resource_owner_id_column: Optional explicit owner id column.
        has_manage_permission: Fast-path flag for ACL manage capability.

    Returns:
        AuthzSqlFilter that can be directly applied to SQL WHERE clause in
        list/search queries.
    """
    if has_manage_permission:
        return AuthzSqlFilter(allow_all=True, deny_all=False, clause=None)

    normalized_action = to_abac_action(action)
    resolved_resource_id_column = resource_id_column
    resolved_resource_owner_id_column = resource_owner_id_column

    if resolved_resource_id_column is None:
        if resource_model is None or not hasattr(resource_model, "id"):
            raise ValueError("resource_id_column is required when resource_model.id is unavailable")
        resolved_resource_id_column = resource_model.id

    if resolved_resource_owner_id_column is None and resource_model is not None and hasattr(resource_model, "owner_id"):
        resolved_resource_owner_id_column = resource_model.owner_id

    resolved_resource_attrs = dict(resource_attr_map or {})
    # Ensure ABAC DSL can resolve :resource.owner_id when owner column exists.
    if resolved_resource_owner_id_column is not None and "resource.owner_id" not in resolved_resource_attrs:
        resolved_resource_attrs["resource.owner_id"] = resolved_resource_owner_id_column

    abac_filter = await _build_abac_resource_filter(
        db_session=db_session,
        tenant_id=tenant_id,
        user_id=user_id,
        user_role=user_role,
        resource_type=resource_type,
        action=normalized_action,
        resource_id_column=resolved_resource_id_column,
        resource_attr_map=resolved_resource_attrs,
    )

    _acl_exists, acl_allows = _build_acl_allows_clause(
        tenant_id=tenant_id,
        user_id=user_id,
        user_role=user_role,
        resource_type=resource_type,
        action=action,
        resource_id_column=resolved_resource_id_column,
        resource_owner_id_column=resolved_resource_owner_id_column,
        has_manage_permission=has_manage_permission,
    )

    if abac_filter.allow_all:
        return AuthzSqlFilter(allow_all=True, deny_all=False, clause=None)
    if abac_filter.deny_all:
        return AuthzSqlFilter(allow_all=False, deny_all=False, clause=acl_allows)
    if abac_filter.clause is None:
        return AuthzSqlFilter(allow_all=False, deny_all=False, clause=acl_allows)
    return AuthzSqlFilter(allow_all=False, deny_all=False, clause=or_(abac_filter.clause, acl_allows))


def _build_acl_allows_clause(
    *,
    tenant_id: int,
    user_id: int,
    user_role: str | None,
    resource_type: ResourceType,
    action: str,
    resource_id_column,
    resource_owner_id_column: ColumnElement | None,
    has_manage_permission: bool,
) -> tuple[ColumnElement[bool], ColumnElement[bool]]:
    """Return ``(acl_exists, acl_allows)`` SQL subexpressions.

    ``acl_exists`` — True when a ResourceAcl row exists for the resource.
    ``acl_allows`` — True when an active ACL explicitly permits the principal
    (owner match, manage permission, or allow-grant without a deny-grant).

    Callers compose the two parts according to their override semantics:
    - ``or_(~acl_exists, acl_allows)`` — classic gate: no ACL passes freely.
    - ``or_(and_(~acl_exists, abac_clause), acl_allows)`` — ACL allow overrides ABAC.
    """
    required_permissions = required_acl_permissions(action)

    resource_acl_base = and_(
        ResourceAcl.tenant_id == tenant_id,
        ResourceAcl.resource_type == resource_type,
        ResourceAcl.resource_id == resource_id_column,
    )

    acl_exists = select(ResourceAcl.id).where(resource_acl_base).exists()
    acl_active = select(ResourceAcl.id).where(resource_acl_base, ResourceAcl.status == "active").exists()

    owner_expr = ResourceAcl.owner_id
    if resource_owner_id_column is not None:
        # ResourceAcl.owner_id has priority; model owner column is fallback for legacy rows.
        owner_expr = func.coalesce(ResourceAcl.owner_id, resource_owner_id_column)
    owner_allow = select(ResourceAcl.id).where(
        resource_acl_base,
        ResourceAcl.status == "active",
        owner_expr == user_id,
    ).exists()

    principal_filters = [
        and_(
            AclGrant.principal_type == "user",
            AclGrant.principal_id == str(user_id),
        )
    ]
    if user_role:
        principal_filters.append(
            and_(
                AclGrant.principal_type == "role",
                AclGrant.principal_id == user_role,
            )
        )

    grant_base = and_(
        AclGrant.tenant_id == tenant_id,
        AclGrant.resource_type == resource_type,
        AclGrant.resource_id == resource_id_column,
        AclGrant.permission.in_(required_permissions),
        or_(*principal_filters),
    )
    grant_deny_exists = select(AclGrant.id).where(grant_base, AclGrant.effect == "deny").exists()
    grant_allow_exists = select(AclGrant.id).where(grant_base, AclGrant.effect == "allow").exists()

    acl_allows = and_(
        acl_active,
        or_(
            owner_allow,
            literal(has_manage_permission),
            and_(~grant_deny_exists, grant_allow_exists),
        ),
    )

    return acl_exists, acl_allows


def _build_acl_resource_clause(
    *,
    tenant_id: int,
    user_id: int,
    user_role: str | None,
    resource_type: ResourceType,
    action: str,
    resource_id_column,
    resource_owner_id_column: ColumnElement | None,
    has_manage_permission: bool,
) -> ColumnElement[bool]:
    """Build ACL SQL predicate for list/search filtering.

    Decision semantics encoded by this clause:
    1) If no ResourceAcl row exists for a resource -> ACL is not applicable.
    2) If ResourceAcl exists but inactive -> deny.
    3) If active, allow when owner/manage/allow-grant matches and no deny-grant.
    """
    acl_exists, acl_allows = _build_acl_allows_clause(
        tenant_id=tenant_id,
        user_id=user_id,
        user_role=user_role,
        resource_type=resource_type,
        action=action,
        resource_id_column=resource_id_column,
        resource_owner_id_column=resource_owner_id_column,
        has_manage_permission=has_manage_permission,
    )
    # ACL only constrains resources with explicit ACL entries.
    return or_(~acl_exists, acl_allows)


async def _get_resource_tag_context(
    *,
    tag_binding_repo: TagBindingRepository,
    tenant_id: int,
    resource_type: ResourceType,
    resource_id: int,
    tag_key_map: dict[int, str],
) -> ResourceTagContext:
    """Load normalized tag context for one resource.

    Produces both exact tags (`key:value`) and per-key max rank used by
    rank_* operators.
    """
    tag_values = await tag_binding_repo.list_tag_values_by_resource(
        tenant_id=tenant_id,
        resource_type=resource_type,
        resource_id=resource_id,
    )
    tags: set[str] = set()
    max_rank_by_key: dict[str, int] = {}
    for tag_value in tag_values:
        tag_key_name = tag_key_map.get(tag_value.key_id)
        if tag_key_name:
            tags.add(f"{tag_key_name}:{tag_value.value}")
            if tag_value.rank is not None:
                existing_rank = max_rank_by_key.get(tag_key_name)
                if existing_rank is None or tag_value.rank > existing_rank:
                    max_rank_by_key[tag_key_name] = tag_value.rank
    return ResourceTagContext(tags=tags, max_rank_by_key=max_rank_by_key)


def _build_policy_clause(
    policy: AbacPolicy,
    user_tag_context: ResourceTagContext,
    tenant_id: int,
    resource_type: ResourceType,
    resource_id_column,
    resource_attr_map: dict[str, ColumnElement],
    user_id: int,
    user_role: str | None = None,
) -> ColumnElement[bool] | bool | None:
    """Parse/validate/compile one ABAC policy expression into SQL.

    Returns:
    - True: policy always allows.
    - SQL expression: row-dependent allow predicate.
    - None: invalid/unsupported policy (or always-false after compile).
    """
    expression = policy.expression
    if not isinstance(expression, str) or not expression.strip():
        logger.warning("Invalid policy expression: %s", expression)
        return None

    registry = build_attr_registry(resource_attr_map.keys())
    try:
        parsed = parse_dsl(expression)
        validate_expr(parsed, registry)
    except (DslParseError, DslValidationError) as exc:
        if _ABAC_STRICT_POLICY_VALIDATION:
            raise AbacPolicyCompileError(f"Invalid ABAC policy expression (policy_id={policy.id})") from exc
        logger.warning("Invalid policy expression: %s", expression)
        logger.debug("Policy expression error: %s", exc)
        return None

    try:
        compiled = _compile_expr(
            parsed,
            user_tags=user_tag_context.tags,
            user_tag_ranks=user_tag_context.max_rank_by_key,
            user_id=user_id,
            user_role=user_role,
            tenant_id=tenant_id,
            resource_type=resource_type,
            resource_id_column=resource_id_column,
            resource_attr_map=resource_attr_map,
        )
    except AbacPolicyCompileError:
        if _ABAC_STRICT_POLICY_VALIDATION:
            raise
        return None
    if compiled is True:
        return True
    if compiled is False:
        return None
    return compiled


def _compile_expr(
    expr: Expr,
    *,
    user_tags: set[str],
    user_tag_ranks: dict[str, int],
    user_id: int,
    user_role: str | None = None,
    tenant_id: int,
    resource_type: ResourceType,
    resource_id_column,
    resource_attr_map: dict[str, ColumnElement],
) -> ColumnElement[bool] | bool:
    """Compile ABAC AST node into SQL boolean expression or constant bool.

    Constant folding is applied during recursion:
    - Returns True/False when expression can be decided locally.
    - Returns SQLAlchemy boolean expression when runtime row data is required.
    """
    if isinstance(expr, TermExpr):
        return _compile_term(
            expr,
            user_tags=user_tags,
            user_tag_ranks=user_tag_ranks,
            user_id=user_id,
            user_role=user_role,
            tenant_id=tenant_id,
            resource_type=resource_type,
            resource_id_column=resource_id_column,
            resource_attr_map=resource_attr_map,
        )
    left = _compile_expr(
        expr.left,
        user_tags=user_tags,
        user_tag_ranks=user_tag_ranks,
        user_id=user_id,
        user_role=user_role,
        tenant_id=tenant_id,
        resource_type=resource_type,
        resource_id_column=resource_id_column,
        resource_attr_map=resource_attr_map,
    )
    right = _compile_expr(
        expr.right,
        user_tags=user_tags,
        user_tag_ranks=user_tag_ranks,
        user_id=user_id,
        user_role=user_role,
        tenant_id=tenant_id,
        resource_type=resource_type,
        resource_id_column=resource_id_column,
        resource_attr_map=resource_attr_map,
    )
    return _combine_expr(expr.op, left, right)


def _combine_expr(op: str, left: ColumnElement[bool] | bool, right: ColumnElement[bool] | bool):
    """Combine two compiled boolean operands with simple constant folding."""
    if op == "and":
        if left is False or right is False:
            return False
        if left is True:
            return right
        if right is True:
            return left
        return and_(left, right)
    if op == "or":
        if left is True or right is True:
            return True
        if left is False:
            return right
        if right is False:
            return left
        return or_(left, right)
    raise AbacPolicyCompileError(f"Unsupported boolean operator: {op}")


def _compile_term(
    term: TermExpr,
    *,
    user_tags: set[str],
    user_tag_ranks: dict[str, int],
    user_id: int,
    user_role: str | None = None,
    tenant_id: int,
    resource_type: ResourceType,
    resource_id_column,
    resource_attr_map: dict[str, ColumnElement],
) -> ColumnElement[bool] | bool:
    """Dispatch one terminal expression to its dedicated compiler."""
    op = term.op
    if op == "has":
        return _compile_has(term, user_tags, tenant_id, resource_type, resource_id_column)
    if op == "contains":
        return _compile_contains(term, user_tags, tenant_id, resource_type, resource_id_column)
    if op == "equals":
        return _compile_equals(term, user_id, user_role, resource_attr_map)
    if op == "in":
        return _compile_in(term, user_id, user_role, resource_attr_map)
    if op in RANK_OPERATORS:
        return _compile_rank_compare(term, user_tag_ranks, tenant_id, resource_type, resource_id_column)
    raise AbacPolicyCompileError(f"Unsupported term operator: {op}")


def _compile_rank_compare(
    term: TermExpr,
    user_tag_ranks: dict[str, int],
    tenant_id: int,
    resource_type: ResourceType,
    resource_id_column,
) -> ColumnElement[bool] | bool:
    """Compile rank comparison between user tag rank and resource tag rank."""
    if not isinstance(term.right, AttrRef):
        return False
    if term.left.name != "user.tags" or term.right.name != "resource.tags":
        return False
    if not term.rank_key:
        return False

    user_rank = user_tag_ranks.get(term.rank_key)
    if user_rank is None:
        return False

    resource_rank_expr = _build_resource_rank_expr(
        tenant_id=tenant_id,
        resource_type=resource_type,
        resource_id_column=resource_id_column,
        rank_key=term.rank_key,
    )

    if term.op == "rank_gte":
        return and_(resource_rank_expr.is_not(None), literal(user_rank) >= resource_rank_expr)
    if term.op == "rank_gt":
        return and_(resource_rank_expr.is_not(None), literal(user_rank) > resource_rank_expr)
    if term.op == "rank_lte":
        return and_(resource_rank_expr.is_not(None), literal(user_rank) <= resource_rank_expr)
    if term.op == "rank_lt":
        return and_(resource_rank_expr.is_not(None), literal(user_rank) < resource_rank_expr)
    if term.op == "rank_eq":
        return and_(resource_rank_expr.is_not(None), literal(user_rank) == resource_rank_expr)
    return False


def _build_resource_rank_expr(
    *,
    tenant_id: int,
    resource_type: ResourceType,
    resource_id_column,
    rank_key: str,
):
    """Build scalar subquery returning max rank for `rank_key` on resource."""
    return (
        select(func.max(TagValue.rank))
        .select_from(TagBinding)
        .join(TagValue, TagBinding.tag_value_id == TagValue.id)
        .join(TagKey, TagValue.key_id == TagKey.id)
        .where(
            TagBinding.tenant_id == tenant_id,
            TagBinding.resource_type == resource_type,
            TagBinding.resource_id == resource_id_column,
            TagKey.name == rank_key,
            TagValue.rank.is_not(None),
        )
        .scalar_subquery()
    )


def _compile_has(
    term: TermExpr,
    user_tags: set[str],
    tenant_id: int,
    resource_type: ResourceType,
    resource_id_column,
) -> ColumnElement[bool] | bool:
    """Compile `has` operator for user/resource tags, including key wildcard."""
    if not isinstance(term.right, Literal):
        return False
    tag_value = term.right.value
    if term.left.name == "user.tags":
        if _is_tag_key_wildcard(tag_value):
            wildcard_key = _extract_tag_key(tag_value)
            if wildcard_key is None:
                return False
            return any(_tag_has_key(user_tag, wildcard_key) for user_tag in user_tags)
        return tag_value in user_tags
    if term.left.name == "resource.tags":
        return _build_any_tags_clause([tag_value], tenant_id, resource_type, resource_id_column)
    return False


def _compile_contains(
    term: TermExpr,
    user_tags: set[str],
    tenant_id: int,
    resource_type: ResourceType,
    resource_id_column,
) -> ColumnElement[bool] | bool:
    """Compile `contains` operator for supported attr pairs only."""
    if not isinstance(term.right, AttrRef):
        return False
    if term.left.name == "user.tags" and term.right.name == "resource.tags":
        return _build_user_contains_resource_clause(
            user_tags,
            tenant_id,
            resource_type,
            resource_id_column,
            scope_keys=term.scope_keys,
        )
    return False


def _compile_equals(
    term: TermExpr,
    user_id: int,
    user_role: str | None,
    resource_attr_map: dict[str, ColumnElement],
) -> ColumnElement[bool] | bool:
    """Compile scalar equality between literals, attrs, and SQL expressions."""
    left_value = _resolve_scalar_attr(term.left, user_id, user_role, resource_attr_map)
    if left_value is None:
        return False
    right_value: ColumnElement | str | int | None
    if isinstance(term.right, AttrRef):
        right_value = _resolve_scalar_attr(term.right, user_id, user_role, resource_attr_map)
    elif isinstance(term.right, Literal):
        right_value = term.right.value
    else:
        return False
    if right_value is None:
        return False
    if isinstance(left_value, ColumnElement):
        return left_value == right_value
    if isinstance(right_value, ColumnElement):
        return right_value == left_value
    return left_value == right_value


def _compile_in(
    term: TermExpr,
    user_id: int,
    user_role: str | None,
    resource_attr_map: dict[str, ColumnElement],
) -> ColumnElement[bool] | bool:
    """Compile membership test (`in`) against a list literal."""
    if not isinstance(term.right, ListLiteral):
        return False
    left_value = _resolve_scalar_attr(term.left, user_id, user_role, resource_attr_map)
    if left_value is None:
        return False
    values = list(term.right.values)
    if isinstance(left_value, ColumnElement):
        return left_value.in_(values)
    return left_value in values


def _resolve_scalar_attr(
    attr: AttrRef,
    user_id: int,
    user_role: str | None,
    resource_attr_map: dict[str, ColumnElement],
) -> ColumnElement | str | int | None:
    """Resolve supported scalar attrs to concrete values/SQL expressions."""
    if attr.name == "user.id":
        return user_id
    if attr.name == "user.role":
        return user_role  # None → equals comparison → evaluates False safely
    if attr.name in resource_attr_map:
        return resource_attr_map[attr.name]
    return None


async def evaluate_single_expression(
    *,
    db_session,
    tenant_id: int,
    user_id: int,
    user_role: str | None,
    resource_type: ResourceType,
    action: str = ABAC_ACTION_READ,
    resource_id: int,
    expression: str,
) -> tuple[bool, str]:
    """Evaluate one expression string against real DB state for a specific resource.

    This is used by simulation/debug paths where callers provide a concrete
    resource id and expression string, and expect an explainable result.

    Returns (allowed, reason_str).
    """
    from sqlalchemy import literal

    from apps.shared.authz.dsl import build_attr_registry, expr_to_human, parse_dsl, validate_expr
    from apps.shared.tag.repository import TagBindingRepository, TagKeyRepository

    tag_key_repo = TagKeyRepository(db_session)
    tag_binding_repo = TagBindingRepository(db_session)
    tag_key_map = {k.id: k.name for k in await tag_key_repo.list_by_tenant(tenant_id)}
    user_tag_context = await _get_resource_tag_context(
        tag_binding_repo=tag_binding_repo,
        tenant_id=tenant_id,
        resource_type=RESOURCE_TYPE_USER,
        resource_id=user_id,
        tag_key_map=tag_key_map,
    )
    # Simulation input only contains resource id, so owner id is resolved here
    # to support ABAC clauses like :resource.owner_id.
    owner_id = await _resolve_owner_id_for_simulation(
        db_session=db_session,
        tenant_id=tenant_id,
        resource_type=resource_type,
        resource_id=resource_id,
    )
    resource_attr_map = _build_resource_literal_attr_map(resource_id, owner_id)
    resource_id_col = resource_attr_map["resource.id"]
    registry = build_attr_registry(resource_attr_map.keys())
    parsed = parse_dsl(expression)
    validate_expr(parsed, registry)
    compiled = _compile_expr(
        parsed,
        user_tags=user_tag_context.tags,
        user_tag_ranks=user_tag_context.max_rank_by_key,
        user_id=user_id,
        user_role=user_role,
        tenant_id=tenant_id,
        resource_type=resource_type,
        resource_id_column=resource_id_col,
        resource_attr_map=resource_attr_map,
    )
    if compiled is True:
        allowed = True
    elif compiled is False:
        allowed = False
    else:
        from sqlalchemy import select

        stmt = select(literal(1)).where(compiled)
        result = await db_session.execute(stmt)
        allowed = result.scalar() is not None
    reason = expr_to_human(parsed)
    return allowed, reason


async def _resolve_owner_id_for_simulation(
    *,
    db_session,
    tenant_id: int,
    resource_type: ResourceType,
    resource_id: int,
) -> int | None:
    """Resolve owner_id for evaluate_single_expression simulation only.

    This helper is intentionally scoped to ABAC policy simulation path and is
    not part of runtime authorization checks.
    """
    resolver = _SIMULATION_OWNER_RESOLVERS.get(resource_type)
    if resolver is not None:
        return await resolver(db_session, tenant_id, resource_id)
    logger.warning(
        "No owner resolver implemented for simulation resource_type=%s (resource_id=%s, tenant_id=%s)",
        resource_type,
        resource_id,
        tenant_id,
    )
    return None


async def _resolve_document_owner_id(db_session, tenant_id: int, resource_id: int) -> int | None:
    stmt = select(Document.owner_id).where(Document.tenant_id == tenant_id, Document.id == resource_id)
    return await db_session.scalar(stmt)


async def _resolve_api_connector_owner_id(db_session, tenant_id: int, resource_id: int) -> int | None:
    stmt = select(ApiConnector.owner_id).where(ApiConnector.tenant_id == tenant_id, ApiConnector.id == resource_id)
    return await db_session.scalar(stmt)


async def _resolve_document_collection_owner_id(db_session, tenant_id: int, resource_id: int) -> int | None:
    stmt = select(DocumentCollection.owner_id).where(
        DocumentCollection.tenant_id == tenant_id,
        DocumentCollection.id == resource_id,
    )
    return await db_session.scalar(stmt)


async def _resolve_data_source_owner_id(db_session, tenant_id: int, resource_id: int) -> int | None:
    stmt = select(DataSource.owner_id).where(DataSource.tenant_id == tenant_id, DataSource.id == resource_id)
    return await db_session.scalar(stmt)


async def _resolve_agent_owner_id(db_session, tenant_id: int, resource_id: int) -> int | None:
    stmt = select(Agent.owner_id).where(Agent.tenant_id == tenant_id, Agent.id == resource_id)
    return await db_session.scalar(stmt)


_SIMULATION_OWNER_RESOLVERS: dict[ResourceType, SimulationOwnerResolver] = {
    RESOURCE_TYPE_DOCUMENT: _resolve_document_owner_id,
    RESOURCE_TYPE_DOCUMENT_COLLECTION: _resolve_document_collection_owner_id,
    RESOURCE_TYPE_API_CONNECTOR: _resolve_api_connector_owner_id,
    RESOURCE_TYPE_DATA_SOURCE: _resolve_data_source_owner_id,
    RESOURCE_TYPE_AGENT: _resolve_agent_owner_id,
}


def _build_user_contains_resource_clause(
    user_tags: set[str],
    tenant_id: int,
    resource_type: ResourceType,
    resource_id_column,
    scope_keys: tuple[str, ...] | None = None,
) -> ColumnElement[bool]:
    """Compile `user.tags contains resource.tags` using NOT EXISTS anti-join.

    Meaning: there must not exist any resource tag outside the user's tag set
    (optionally limited to scoped keys).
    """
    allowed_conditions = _build_tag_conditions(sorted(user_tags))
    subquery = (
        select(TagBinding.id)
        .join(TagValue, TagBinding.tag_value_id == TagValue.id)
        .join(TagKey, TagValue.key_id == TagKey.id)
        .where(
            TagBinding.tenant_id == tenant_id,
            TagBinding.resource_type == resource_type,
            TagBinding.resource_id == resource_id_column,
        )
    )
    if scope_keys:
        subquery = subquery.where(TagKey.name.in_(list(scope_keys)))
    if allowed_conditions:
        subquery = subquery.where(~or_(*allowed_conditions))
    return ~subquery.exists()


def _build_any_tags_clause(
    required_tags: list[str],
    tenant_id: int,
    resource_type: ResourceType,
    resource_id_column,
) -> ColumnElement[bool]:
    """Build SQL clause requiring resource to match at least one tag."""
    tag_conditions = _build_tag_conditions(required_tags)
    if not tag_conditions:
        return false()
    subquery = (
        select(TagBinding.resource_id)
        .join(TagValue, TagBinding.tag_value_id == TagValue.id)
        .join(TagKey, TagValue.key_id == TagKey.id)
        .where(
            TagBinding.tenant_id == tenant_id,
            TagBinding.resource_type == resource_type,
            or_(*tag_conditions),
        )
    )
    return resource_id_column.in_(subquery)


def _build_all_tags_clause(
    required_tags: list[str],
    tenant_id: int,
    resource_type: ResourceType,
    resource_id_column,
) -> ColumnElement[bool]:
    """Build SQL clause requiring resource to match all provided tags."""
    tag_conditions = _build_tag_conditions(required_tags)
    if not tag_conditions:
        return false()
    required_count = len(tag_conditions)
    tag_key_value = func.concat(TagKey.name, ":", TagValue.value)
    subquery = (
        select(TagBinding.resource_id)
        .join(TagValue, TagBinding.tag_value_id == TagValue.id)
        .join(TagKey, TagValue.key_id == TagKey.id)
        .where(
            TagBinding.tenant_id == tenant_id,
            TagBinding.resource_type == resource_type,
            or_(*tag_conditions),
        )
        .group_by(TagBinding.resource_id)
        .having(func.count(func.distinct(tag_key_value)) >= required_count)
    )
    return resource_id_column.in_(subquery)


def _build_tag_conditions(required_tags: list[str]) -> list[ColumnElement[bool]]:
    """Convert `key:value` tag literals into SQL predicates."""
    conditions: list[ColumnElement[bool]] = []
    for tag in required_tags:
        key, value = _split_tag(tag)
        if not key or not value:
            continue
        if value == "*":
            conditions.append(TagKey.name == key)
        else:
            conditions.append(and_(TagKey.name == key, TagValue.value == value))
    return conditions


def _split_tag(tag: str) -> tuple[str | None, str | None]:
    """Split one `key:value` tag literal into (key, value)."""
    if ":" not in tag:
        return None, None
    key, value = tag.split(":", 1)
    return key, value


def _is_tag_key_wildcard(tag: str) -> bool:
    """Return True for wildcard form like `dept:*`."""
    _key, value = _split_tag(tag)
    return value == "*"


def _extract_tag_key(tag: str) -> str | None:
    """Extract key from tag literal; returns None for invalid input."""
    key, _value = _split_tag(tag)
    if not key:
        return None
    return key


def _tag_has_key(tag: str, key: str) -> bool:
    """Check whether tag literal belongs to a given key."""
    tag_key, _tag_value = _split_tag(tag)
    return tag_key == key


async def evaluate_resource_action(
    *,
    db_session,
    tenant_id: int,
    user_id: int,
    user_role: str | None,
    resource_type: ResourceType,
    resource_id: int,
    resource_owner_id: int | None,
    action: str = ABAC_ACTION_READ,
    has_manage_permission: bool = False,
) -> bool:
    """Evaluate ABAC+ACL authorization for one concrete resource instance.

    Evaluation order:
    1) ACL evaluated first to collect supplemental allow signal.
    2) ABAC evaluated as baseline policy signal.
    3) Final decision is additive: ``ABAC_ALLOW OR ACL_ALLOW``.

    Return policy:
    - ACL allow -> True
    - ABAC allow -> True
    - Otherwise -> False
    """
    # Step 1: ACL supplemental signal.
    acl_decision = await evaluate_acl_action(
        db=db_session,
        acl_input=AclCheckInput(
            tenant_id=tenant_id,
            user_id=user_id,
            user_role=user_role,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            resource_owner_id=resource_owner_id,
            has_manage_permission=has_manage_permission,
        ),
    )
    if acl_decision == AclDecision.ALLOW:
        return True

    # Step 2: ABAC baseline signal.
    normalized_action = to_abac_action(action)
    resource_attr_map = _build_resource_literal_attr_map(resource_id, resource_owner_id)
    resource_id_col = resource_attr_map["resource.id"]
    abac_filter = await _build_abac_resource_filter(
        db_session=db_session,
        tenant_id=tenant_id,
        user_id=user_id,
        user_role=user_role,
        resource_type=resource_type,
        action=normalized_action,
        resource_id_column=resource_id_col,
        resource_attr_map=resource_attr_map,
    )

    if abac_filter.deny_all:
        return False
    if abac_filter.allow_all:
        return True
    if abac_filter.clause is None:
        return False
    stmt = select(literal(1)).where(abac_filter.clause)
    result = await db_session.execute(stmt)
    return result.scalar() is not None
