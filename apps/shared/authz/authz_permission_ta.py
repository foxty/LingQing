"""Tenant-app permission catalog with unified read/write/manage semantics."""

from __future__ import annotations

from dataclasses import dataclass

from apps.shared.authz.authz_permission import AuthzPermissionActions, action_implies, build_resource_permission


def _perm(resource: str, action: str) -> str:
    return build_resource_permission(resource, action)


@dataclass(frozen=True)
class TenantAppPermissions:
    """Permission constants for tenant app domain."""

    TENANT_ADMIN: str = "tenant.admin"

    TENANT_SETTINGS_READ: str = _perm("tenant.settings", AuthzPermissionActions.READ)
    TENANT_SETTINGS_WRITE: str = _perm("tenant.settings", AuthzPermissionActions.WRITE)
    TENANT_SETTINGS_MANAGE: str = _perm("tenant.settings", AuthzPermissionActions.MANAGE)

    USERS_READ: str = _perm("users", AuthzPermissionActions.READ)
    USERS_WRITE: str = _perm("users", AuthzPermissionActions.WRITE)
    USERS_MANAGE: str = _perm("users", AuthzPermissionActions.MANAGE)

    RBAC_READ: str = _perm("rbac", AuthzPermissionActions.READ)
    RBAC_WRITE: str = _perm("rbac", AuthzPermissionActions.WRITE)
    RBAC_MANAGE: str = _perm("rbac", AuthzPermissionActions.MANAGE)

    AUTH_PROVIDERS_READ: str = _perm("auth.providers", AuthzPermissionActions.READ)
    AUTH_PROVIDERS_WRITE: str = _perm("auth.providers", AuthzPermissionActions.WRITE)
    AUTH_PROVIDERS_MANAGE: str = _perm("auth.providers", AuthzPermissionActions.MANAGE)

    DATA_SOURCES_READ: str = _perm("data_sources", AuthzPermissionActions.READ)
    DATA_SOURCES_WRITE: str = _perm("data_sources", AuthzPermissionActions.WRITE)
    DATA_SOURCES_MANAGE: str = _perm("data_sources", AuthzPermissionActions.MANAGE)

    DASHBOARDS_READ: str = _perm("dashboards", AuthzPermissionActions.READ)
    DASHBOARDS_WRITE: str = _perm("dashboards", AuthzPermissionActions.WRITE)
    DASHBOARDS_MANAGE: str = _perm("dashboards", AuthzPermissionActions.MANAGE)
    DASHBOARDS_SQL_EXECUTE: str = "dashboards.sql.execute"

    CHAT_READ: str = _perm("chat", AuthzPermissionActions.READ)
    CHAT_WRITE: str = _perm("chat", AuthzPermissionActions.WRITE)
    CHAT_MANAGE: str = _perm("chat", AuthzPermissionActions.MANAGE)
    CHAT_ACCESS: str = "chat.access"

    APPS_READ: str = _perm("apps", AuthzPermissionActions.READ)
    APPS_WRITE: str = _perm("apps", AuthzPermissionActions.WRITE)
    APPS_MANAGE: str = _perm("apps", AuthzPermissionActions.MANAGE)

    DOCUMENTS_READ: str = _perm("documents", AuthzPermissionActions.READ)
    DOCUMENTS_WRITE: str = _perm("documents", AuthzPermissionActions.WRITE)
    DOCUMENTS_MANAGE: str = _perm("documents", AuthzPermissionActions.MANAGE)

    TAGS_READ: str = _perm("tags", AuthzPermissionActions.READ)
    TAGS_WRITE: str = _perm("tags", AuthzPermissionActions.WRITE)
    TAGS_MANAGE: str = _perm("tags", AuthzPermissionActions.MANAGE)

    AUDIT_READ: str = _perm("audit", AuthzPermissionActions.READ)
    AUDIT_WRITE: str = _perm("audit", AuthzPermissionActions.WRITE)
    AUDIT_MANAGE: str = _perm("audit", AuthzPermissionActions.MANAGE)

    ARTIFACTS_READ: str = _perm("artifacts", AuthzPermissionActions.READ)
    ARTIFACTS_WRITE: str = _perm("artifacts", AuthzPermissionActions.WRITE)
    ARTIFACTS_MANAGE: str = _perm("artifacts", AuthzPermissionActions.MANAGE)

    REPORTS_READ: str = _perm("reports", AuthzPermissionActions.READ)
    REPORTS_WRITE: str = _perm("reports", AuthzPermissionActions.WRITE)
    REPORTS_MANAGE: str = _perm("reports", AuthzPermissionActions.MANAGE)

    SCHEDULED_TASKS_READ: str = _perm("scheduled_tasks", AuthzPermissionActions.READ)
    SCHEDULED_TASKS_WRITE: str = _perm("scheduled_tasks", AuthzPermissionActions.WRITE)
    SCHEDULED_TASKS_MANAGE: str = _perm("scheduled_tasks", AuthzPermissionActions.MANAGE)

    API_CONNECTORS_READ: str = _perm("api_connectors", AuthzPermissionActions.READ)
    API_CONNECTORS_WRITE: str = _perm("api_connectors", AuthzPermissionActions.WRITE)
    API_CONNECTORS_MANAGE: str = _perm("api_connectors", AuthzPermissionActions.MANAGE)

    # Backward-compatible alias retained for existing call sites.
    API_CONNECTORS_CREATE: str = "api_connectors.create"

    SKILLS_READ: str = _perm("skills", AuthzPermissionActions.READ)
    SKILLS_WRITE: str = _perm("skills", AuthzPermissionActions.WRITE)
    SKILLS_MANAGE: str = _perm("skills", AuthzPermissionActions.MANAGE)

    AGENTS_READ: str = _perm("agents", AuthzPermissionActions.READ)
    AGENTS_WRITE: str = _perm("agents", AuthzPermissionActions.WRITE)
    AGENTS_MANAGE: str = _perm("agents", AuthzPermissionActions.MANAGE)


TA_ALL_PERMISSIONS: set[str] = {
    value
    for key, value in TenantAppPermissions.__dict__.items()
    if key.isupper() and isinstance(value, str)
}


def is_known_ta_permission(permission: str) -> bool:
    return permission in TA_ALL_PERMISSIONS


def ta_permission_implies(granted_permission: str, required_permission: str) -> bool:
    """Check implication for tenant-app permissions.

    For non resource-action permissions (tenant.admin, dashboards.sql.execute),
    implication is exact match unless tenant.admin is granted.
    """
    if granted_permission == TenantAppPermissions.TENANT_ADMIN:
        return True

    if granted_permission == required_permission:
        return True

    granted_parts = granted_permission.rsplit(".", 1)
    required_parts = required_permission.rsplit(".", 1)
    if len(granted_parts) != 2 or len(required_parts) != 2:
        return False
    granted_resource, granted_action = granted_parts
    required_resource, required_action = required_parts
    if granted_resource != required_resource:
        return False
    try:
        return action_implies(granted_action, required_action)
    except ValueError:
        return False
