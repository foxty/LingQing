"""Backward-compatible tenant-app RBAC exports.

This module preserves legacy import paths used by tests and scripts:
`apps.shared.authz.rbac`.
"""

from apps.shared.authz.ta_rbac import DEFAULT_ROLE_PERMISSIONS, EffectiveRBAC, get_effective_rbac, role_has_permission

__all__ = [
    "DEFAULT_ROLE_PERMISSIONS",
    "EffectiveRBAC",
    "get_effective_rbac",
    "role_has_permission",
]
