"""Tenant manager permission identifiers for RBAC."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TenantManagerPermissions:
    """Permission constants for control-plane (tenant manager) domain."""

    TENANTS_READ: str = "cp.tenants.read"
    TENANTS_CREATE: str = "cp.tenants.create"
    LIFECYCLE_PROVISION: str = "cp.lifecycle.provision"
    LIFECYCLE_LOCK: str = "cp.lifecycle.lock"
    LIFECYCLE_UNLOCK: str = "cp.lifecycle.unlock"
    AUDIT_READ: str = "cp.audit.read"


TM_ALL_PERMISSIONS: set[str] = {
    TenantManagerPermissions.TENANTS_READ,
    TenantManagerPermissions.TENANTS_CREATE,
    TenantManagerPermissions.LIFECYCLE_PROVISION,
    TenantManagerPermissions.LIFECYCLE_LOCK,
    TenantManagerPermissions.LIFECYCLE_UNLOCK,
    TenantManagerPermissions.AUDIT_READ,
}


def is_known_tm_permission(permission: str) -> bool:
    return permission in TM_ALL_PERMISSIONS
