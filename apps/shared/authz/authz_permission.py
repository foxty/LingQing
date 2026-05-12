"""Shared authorization permission primitives.

This module defines a unified action vocabulary and implication rules used by
resource permissions across domains.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.shared.domain.types import (
    AUTHZ_ACTION_MANAGE,
    AUTHZ_ACTION_READ,
    AUTHZ_ACTION_WRITE,
    normalize_authz_action,
)


@dataclass(frozen=True)
class AuthzPermissionActions:
    """Canonical action names for resource authorization."""

    READ: str = AUTHZ_ACTION_READ
    WRITE: str = AUTHZ_ACTION_WRITE
    MANAGE: str = AUTHZ_ACTION_MANAGE


def action_implies(granted_action: str, required_action: str) -> bool:
    """Return True when granted_action satisfies required_action.

    Implication chain:
    - manage -> write -> read
    - write  -> read
    """
    granted = normalize_authz_action(granted_action)
    required = normalize_authz_action(required_action)

    if granted == required:
        return True
    if granted == AUTHZ_ACTION_MANAGE:
        return True
    return granted == AUTHZ_ACTION_WRITE and required == AUTHZ_ACTION_READ


def build_resource_permission(resource: str, action: str, *, prefix: str | None = None) -> str:
    normalized_action = normalize_authz_action(action)
    normalized_resource = resource.strip().lower()
    if not normalized_resource:
        raise ValueError("resource cannot be empty")
    if prefix:
        return f"{prefix}.{normalized_resource}.{normalized_action}"
    return f"{normalized_resource}.{normalized_action}"
