"""Agent datascope delegation for one chat turn.

Normal authz (``evaluate_resource_action``) is unchanged: it answers whether
the user can open a KB/DS/API in the product.

Chat tools pass ``delegated_ids`` — the agent's attached resource IDs — only
when the invoker owns the agent or has an explicit agent share. That extra
read applies to this call only. Explicit ACL deny still wins.
"""

from __future__ import annotations

from collections.abc import Collection

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from apps.shared.authz.authz_query_builder import AuthzSqlFilter, evaluate_resource_action
from apps.shared.db.models import AclGrant
from apps.shared.domain.types import (
    ABAC_ACTION_READ,
    ACL_EFFECT_ALLOW,
    ACL_EFFECT_DENY,
    ACL_PERMISSION_MANAGE,
    ACL_PERMISSION_READ,
    ACL_PERMISSION_WRITE,
    ACL_PRINCIPAL_ROLE,
    ACL_PRINCIPAL_USER,
    RESOURCE_TYPE_AGENT,
    ResourceType,
    required_acl_permissions,
    to_abac_action,
)


async def has_agent_delegation(
    db: AsyncSession,
    *,
    tenant_id: int,
    agent_id: int,
    user_id: int,
    owner_id: int | None,
) -> bool:
    """True if this user may use the agent's attached datascope in chat.

    Owner always can. Otherwise they need an explicit allow grant on the agent
    (a share). Being able to list the agent via ABAC is not enough.
    """
    if owner_id is not None and owner_id == user_id:
        return True
    grant_id = await db.scalar(
        select(AclGrant.id).where(
            AclGrant.tenant_id == tenant_id,
            AclGrant.resource_type == RESOURCE_TYPE_AGENT,
            AclGrant.resource_id == agent_id,
            AclGrant.principal_type == ACL_PRINCIPAL_USER,
            AclGrant.principal_id == str(user_id),
            AclGrant.effect == ACL_EFFECT_ALLOW,
            AclGrant.permission.in_((ACL_PERMISSION_READ, ACL_PERMISSION_WRITE, ACL_PERMISSION_MANAGE)),
        )
    )
    return grant_id is not None


async def filter_explicit_deny_ids(
    db: AsyncSession,
    *,
    tenant_id: int,
    user_id: int,
    user_role: str | None,
    resource_type: ResourceType,
    resource_ids: Collection[int],
    action: str = ABAC_ACTION_READ,
) -> list[int]:
    """Keep IDs that do not have an explicit ACL deny for this user or role.

    Delegation never overrides deny. Chat uses this to clip the agent's
    attached set before treating those IDs as readable.
    """
    ids = [int(item) for item in resource_ids]
    if not ids:
        return []
    principal_filters = [
        and_(AclGrant.principal_type == ACL_PRINCIPAL_USER, AclGrant.principal_id == str(user_id)),
    ]
    if user_role:
        principal_filters.append(
            and_(AclGrant.principal_type == ACL_PRINCIPAL_ROLE, AclGrant.principal_id == user_role),
        )
    denied = set(
        (
            await db.execute(
                select(AclGrant.resource_id).where(
                    AclGrant.tenant_id == tenant_id,
                    AclGrant.resource_type == resource_type,
                    AclGrant.resource_id.in_(ids),
                    AclGrant.permission.in_(required_acl_permissions(action)),
                    AclGrant.effect == ACL_EFFECT_DENY,
                    or_(*principal_filters),
                )
            )
        )
        .scalars()
        .all()
    )
    return [item for item in ids if item not in denied]


async def allows_delegated_read(
    *,
    db_session: AsyncSession,
    tenant_id: int,
    user_id: int,
    user_role: str | None,
    resource_type: ResourceType,
    resource_id: int,
    resource_owner_id: int | None,
    action: str = ABAC_ACTION_READ,
    has_manage_permission: bool = False,
    delegated_ids: Collection[int] | None = None,
) -> bool:
    """True if the user already has access, or this id is on the agent's datascope.

    ``delegated_ids`` is the agent's attached KB/DS/API ids for this chat turn.
    Omit it (None) on HTTP/catalog callers. Write actions never use it.
    """
    allowed = await evaluate_resource_action(
        db_session=db_session,
        tenant_id=tenant_id,
        user_id=user_id,
        user_role=user_role,
        resource_type=resource_type,
        resource_id=resource_id,
        resource_owner_id=resource_owner_id,
        action=action,
        has_manage_permission=has_manage_permission,
    )
    if allowed:
        return True
    if to_abac_action(action) != ABAC_ACTION_READ:
        return False
    if not delegated_ids or resource_id not in delegated_ids:
        return False
    usable = await filter_explicit_deny_ids(
        db_session,
        tenant_id=tenant_id,
        user_id=user_id,
        user_role=user_role,
        resource_type=resource_type,
        resource_ids=[resource_id],
        action=action,
    )
    return bool(usable)


def combine_agent_scope(
    *,
    user_scope: AuthzSqlFilter,
    id_column: ColumnElement,
    allowed_ids: list[int] | None,
    delegate: bool,
) -> AuthzSqlFilter:
    """Clip a SQL authz filter to the agent's attached IDs (A).

    ``allowed_ids is None``: no agent clip (system Agent One).
    Empty ``allowed_ids``: deny all.
    ``delegate``: readable set is A (caller already subtracted explicit denies).
    Otherwise: readable set is user ACL ∩ A.
    """
    if allowed_ids is None:
        return user_scope
    if not allowed_ids:
        return AuthzSqlFilter(allow_all=False, deny_all=True, clause=None)

    allowed_clause = id_column.in_(allowed_ids)
    if delegate or user_scope.allow_all:
        return AuthzSqlFilter(allow_all=False, deny_all=False, clause=allowed_clause)
    if user_scope.deny_all or user_scope.clause is None:
        return AuthzSqlFilter(allow_all=False, deny_all=True, clause=None)
    return AuthzSqlFilter(allow_all=False, deny_all=False, clause=and_(user_scope.clause, allowed_clause))
