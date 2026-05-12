"""Shared actor context model for service-layer permission checks."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ActorContext:
    tenant_id: int
    user_id: int
    user_role: str
