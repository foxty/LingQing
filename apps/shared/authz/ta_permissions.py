"""Backward-compatible tenant-app permission exports.

Canonical permission definitions now live in `authz_permission_ta.py`.
"""

from apps.shared.authz.authz_permission_ta import (
    TA_ALL_PERMISSIONS,
    TenantAppPermissions,
    is_known_ta_permission,
    ta_permission_implies,
)

__all__ = [
    "TenantAppPermissions",
    "TA_ALL_PERMISSIONS",
    "is_known_ta_permission",
    "ta_permission_implies",
]
