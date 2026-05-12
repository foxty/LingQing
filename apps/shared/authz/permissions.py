"""Backward-compatible tenant-app permission exports.

This module preserves legacy import paths used by tests and older code:
`apps.shared.authz.permissions`.
"""

from apps.shared.authz.ta_permissions import TA_ALL_PERMISSIONS, TenantAppPermissions, is_known_ta_permission

# Legacy alias expected across tests and existing modules.
Permissions = TenantAppPermissions
ALL_PERMISSIONS = TA_ALL_PERMISSIONS


def is_known_permission(permission: str) -> bool:
    return is_known_ta_permission(permission)


__all__ = ["Permissions", "ALL_PERMISSIONS", "is_known_permission"]
