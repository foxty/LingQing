"""Domain rules for tenant identity admin."""

from __future__ import annotations

from typing import Protocol

from apps.shared.external_identity.domain import validate_policy

__all__ = ["can_enable_force_sso", "validate_policy", "UserProvisionerPort"]


def can_enable_force_sso(break_glass_admin_count: int) -> bool:
    """Force SSO requires at least one active break-glass admin."""
    return break_glass_admin_count >= 1


class UserProvisionerPort(Protocol):
    """Creates an internal user when approving a pending identity with no match."""

    async def create_jit_member(
        self,
        *,
        tenant_id: int,
        email: str | None,
        display_name: str | None,
    ) -> int:
        """Return the new user's id."""
        ...
