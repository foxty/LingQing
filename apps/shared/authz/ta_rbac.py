"""Tenant-app RBAC resolution."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.authz.ta_permissions import TenantAppPermissions, ta_permission_implies

DEFAULT_ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {
        TenantAppPermissions.TENANT_ADMIN,
        TenantAppPermissions.TENANT_SETTINGS_READ,
        TenantAppPermissions.TENANT_SETTINGS_WRITE,
        TenantAppPermissions.USERS_MANAGE,
        TenantAppPermissions.RBAC_MANAGE,
        TenantAppPermissions.AUTH_PROVIDERS_MANAGE,
        TenantAppPermissions.DATA_SOURCES_READ,
        TenantAppPermissions.DATA_SOURCES_WRITE,
        TenantAppPermissions.DASHBOARDS_WRITE,
        TenantAppPermissions.DASHBOARDS_SQL_EXECUTE,
        TenantAppPermissions.CHAT_ACCESS,
        TenantAppPermissions.APPS_WRITE,
        TenantAppPermissions.DOCUMENTS_READ,
        TenantAppPermissions.DOCUMENTS_WRITE,
        TenantAppPermissions.TAGS_READ,
        TenantAppPermissions.TAGS_MANAGE,
        TenantAppPermissions.AUDIT_READ,
        TenantAppPermissions.ARTIFACTS_MANAGE,
        TenantAppPermissions.REPORTS_WRITE,
        TenantAppPermissions.SCHEDULED_TASKS_WRITE,
        TenantAppPermissions.API_CONNECTORS_CREATE,
        TenantAppPermissions.API_CONNECTORS_MANAGE,
        TenantAppPermissions.SKILLS_READ,
        TenantAppPermissions.SKILLS_MANAGE,
        TenantAppPermissions.AGENTS_READ,
        TenantAppPermissions.AGENTS_WRITE,
        TenantAppPermissions.AGENTS_MANAGE,
    },
    "member": {
        TenantAppPermissions.DASHBOARDS_WRITE,
        TenantAppPermissions.DASHBOARDS_SQL_EXECUTE,
        TenantAppPermissions.CHAT_ACCESS,
        TenantAppPermissions.APPS_WRITE,
        TenantAppPermissions.DATA_SOURCES_READ,
        TenantAppPermissions.DATA_SOURCES_WRITE,
        TenantAppPermissions.DOCUMENTS_READ,
        TenantAppPermissions.DOCUMENTS_WRITE,
        TenantAppPermissions.TAGS_READ,
        TenantAppPermissions.REPORTS_WRITE,
        TenantAppPermissions.SCHEDULED_TASKS_WRITE,
        TenantAppPermissions.API_CONNECTORS_CREATE,
        TenantAppPermissions.SKILLS_READ,
        TenantAppPermissions.AGENTS_READ,
        TenantAppPermissions.AGENTS_WRITE,
    },
    "viewer": {
        TenantAppPermissions.DASHBOARDS_SQL_EXECUTE,
        TenantAppPermissions.DATA_SOURCES_READ,
        TenantAppPermissions.DOCUMENTS_READ,
        TenantAppPermissions.TAGS_READ,
        TenantAppPermissions.SKILLS_READ,
        TenantAppPermissions.AGENTS_READ,
    },
}


@dataclass(frozen=True)
class EffectiveRBAC:
    default_role_key: str
    roles: dict[str, set[str]]


async def get_effective_rbac(db: AsyncSession, tenant_id: int) -> EffectiveRBAC:
    """Get effective RBAC configuration for a tenant app tenant."""
    return EffectiveRBAC(
        default_role_key="viewer",
        roles={k: set(v) for k, v in DEFAULT_ROLE_PERMISSIONS.items()},
    )


async def role_has_permission(db: AsyncSession, tenant_id: int, role_key: str, permission: str) -> bool:
    """Check if role_key grants permission within tenant app."""
    effective = await get_effective_rbac(db, tenant_id)

    if permission == TenantAppPermissions.TENANT_ADMIN:
        return permission in effective.roles.get(role_key, set())

    role_permissions = effective.roles.get(role_key, set())
    if TenantAppPermissions.TENANT_ADMIN in role_permissions:
        return True
    if permission in role_permissions:
        return True
    return any(ta_permission_implies(granted, permission) for granted in role_permissions)
