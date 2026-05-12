"""Tenant-manager RBAC resolution."""

from apps.shared.authz.tm_permissions import TenantManagerPermissions

PLATFORM_ROLES: set[str] = {"platform_admin", "platform_ops"}

TM_ROLE_PERMISSIONS: dict[str, set[str]] = {
    "platform_admin": {
        TenantManagerPermissions.TENANTS_READ,
        TenantManagerPermissions.TENANTS_CREATE,
        TenantManagerPermissions.LIFECYCLE_PROVISION,
        TenantManagerPermissions.LIFECYCLE_LOCK,
        TenantManagerPermissions.LIFECYCLE_UNLOCK,
        TenantManagerPermissions.AUDIT_READ,
    },
    "platform_ops": {
        TenantManagerPermissions.TENANTS_READ,
        TenantManagerPermissions.LIFECYCLE_PROVISION,
        TenantManagerPermissions.LIFECYCLE_LOCK,
        TenantManagerPermissions.LIFECYCLE_UNLOCK,
        TenantManagerPermissions.AUDIT_READ,
    },
}


def role_has_tm_permission(role: str, permission: str) -> bool:
    """Check if platform role has required tenant-manager permission."""
    role_permissions = TM_ROLE_PERMISSIONS.get(role, set())
    return permission in role_permissions
