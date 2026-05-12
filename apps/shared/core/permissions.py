"""Compatibility exports for authorization permissions."""

from apps.shared.authz.permissions import ALL_PERMISSIONS, Permissions, is_known_permission

__all__ = ["Permissions", "ALL_PERMISSIONS", "is_known_permission"]
