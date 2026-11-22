"""Tenant membership and user account lifecycle values (mirror DB columns)."""

from __future__ import annotations

import enum


class MembershipStatus(enum.StrEnum):
    """Tenant membership lifecycle within one tenant."""

    ACTIVE = "active"
    INACTIVE = "inactive"


class UserAccountStatus(enum.StrEnum):
    """Global user account status."""

    ACTIVE = "active"
    INACTIVE = "inactive"