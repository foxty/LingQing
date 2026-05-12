"""Artifact access control helpers.

Reusable across routers for ownership/sharing/artifacts.manage checks.
Authorization policy lives here; ArtifactRepository only loads data (e.g. shares).
"""

from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.authz.acl import AclCheckInput, AclDecision, evaluate_acl_action
from apps.shared.authz.ta_permissions import TenantAppPermissions
from apps.shared.authz.ta_rbac import role_has_permission
from apps.shared.core.exceptions import AuthorizationError, ResourceNotFoundError
from apps.shared.db.models import Artifact


async def _require_artifact_access(
    *,
    db: AsyncSession,
    tenant_id: int,
    user_id: int,
    user_role: str,
    artifact_type: str,
    resource_id: int,
    operation: Literal["read", "write"] = "read",
) -> Artifact:
    """Resolve artifact by resource and enforce access."""
    stmt = select(Artifact).where(
        Artifact.tenant_id == tenant_id,
        Artifact.artifact_type == artifact_type,
        Artifact.resource_id == resource_id,
    )
    result = await db.execute(stmt)
    artifact = result.scalar_one_or_none()
    if not artifact:
        raise ResourceNotFoundError(f"{artifact_type} {resource_id} not found")

    has_manage = await role_has_permission(db, tenant_id, user_role, TenantAppPermissions.ARTIFACTS_MANAGE)

    effective_owner_id = artifact.owner_id

    acl_decision = await evaluate_acl_action(
        db=db,
        acl_input=AclCheckInput(
            tenant_id=tenant_id,
            user_id=user_id,
            user_role=user_role,
            resource_type=artifact_type,
            resource_id=resource_id,
            action=operation,
            resource_owner_id=effective_owner_id,
            has_manage_permission=has_manage,
        ),
    )
    if acl_decision == AclDecision.ALLOW:
        return artifact
    if acl_decision == AclDecision.DENY:
        raise AuthorizationError("Access denied")

    # ACL is not configured for this resource. Owner or artifacts.manage can still access.
    owner_id = effective_owner_id
    if has_manage or owner_id == user_id:
        return artifact
    raise AuthorizationError("Access denied")


class ArtifactAccessGuard:
    """Reusable guard for artifact read/write/owner-manage checks."""

    def __init__(
        self,
        *,
        db: AsyncSession,
        tenant_id: int,
        user_id: int,
        user_role: str,
        artifact_type: str,
    ):
        self._db = db
        self._tenant_id = tenant_id
        self._user_id = user_id
        self._user_role = user_role
        self._artifact_type = artifact_type
        self._has_manage: bool | None = None

    async def _get_has_manage(self) -> bool:
        if self._has_manage is None:
            self._has_manage = await role_has_permission(
                self._db,
                self._tenant_id,
                self._user_role,
                TenantAppPermissions.ARTIFACTS_MANAGE,
            )
        return self._has_manage

    async def _require(self, *, resource_id: int, operation: Literal["read", "write"]) -> Artifact:
        return await _require_artifact_access(
            db=self._db,
            tenant_id=self._tenant_id,
            user_id=self._user_id,
            user_role=self._user_role,
            artifact_type=self._artifact_type,
            resource_id=resource_id,
            operation=operation,
        )

    async def require_read(self, *, resource_id: int) -> Artifact:
        return await self._require(resource_id=resource_id, operation="read")

    async def require_write(self, *, resource_id: int) -> Artifact:
        return await self._require(resource_id=resource_id, operation="write")

    async def require_owner_or_manage(self, *, resource_id: int, allow_shared_write: bool) -> Artifact:
        artifact = await self.require_read(resource_id=resource_id)
        owner_id = artifact.owner_id
        if owner_id == self._user_id:
            return artifact
        has_manage = await self._get_has_manage()
        if has_manage:
            return artifact
        if allow_shared_write:
            await self.require_write(resource_id=resource_id)
            return artifact
        raise AuthorizationError("Access denied")
