"""Unified ACL evaluator helpers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import AclGrant, ResourceAcl
from apps.shared.domain.types import required_acl_permissions


class AclDecision(StrEnum):
    """Tri-state ACL decision for caller-side fallback orchestration."""

    ALLOW = "allow"
    DENY = "deny"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class AclCheckInput:
    """Input payload for ACL checks."""

    tenant_id: int
    user_id: int
    user_role: str | None
    resource_type: str
    resource_id: int
    action: str
    resource_owner_id: int | None = None
    has_manage_permission: bool = False


async def evaluate_acl_action(*, db: AsyncSession, acl_input: AclCheckInput) -> AclDecision:
    """Evaluate ACL decision for one resource instance.

    Decision order:
    1) Resource ACL existence/status gate
    2) Owner / manage fast-path
    3) Explicit grants: deny first, then allow
    4) Implicit deny if ACL exists but no matching allow
    """
    resource_stmt = select(ResourceAcl).where(
        ResourceAcl.tenant_id == acl_input.tenant_id,
        ResourceAcl.resource_type == acl_input.resource_type,
        ResourceAcl.resource_id == acl_input.resource_id,
    )
    resource_acl = (await db.execute(resource_stmt)).scalar_one_or_none()
    if resource_acl is None:
        return AclDecision.NOT_APPLICABLE

    if resource_acl.status != "active":
        return AclDecision.DENY

    effective_owner_id = resource_acl.owner_id if resource_acl.owner_id is not None else acl_input.resource_owner_id
    if effective_owner_id is not None and effective_owner_id == acl_input.user_id:
        return AclDecision.ALLOW

    if acl_input.has_manage_permission:
        return AclDecision.ALLOW

    required_permissions = required_acl_permissions(acl_input.action)

    principal_filters = [
        and_(
            AclGrant.principal_type == "user",
            AclGrant.principal_id == str(acl_input.user_id),
        )
    ]
    if acl_input.user_role:
        principal_filters.append(
            and_(
                AclGrant.principal_type == "role",
                AclGrant.principal_id == acl_input.user_role,
            )
        )

    grant_stmt = select(AclGrant.effect).where(
        AclGrant.tenant_id == acl_input.tenant_id,
        AclGrant.resource_type == acl_input.resource_type,
        AclGrant.resource_id == acl_input.resource_id,
        AclGrant.permission.in_(required_permissions),
        or_(*principal_filters),
    )
    effects = [row[0].strip().lower() for row in (await db.execute(grant_stmt)).all()]

    if any(effect == "deny" for effect in effects):
        return AclDecision.DENY
    if any(effect == "allow" for effect in effects):
        return AclDecision.ALLOW
    return AclDecision.DENY
