"""Shared DTOs for user domain."""

from apps.shared.schemas.principal import BackwardCompatibleUserPrincipal


class UserDTO(BackwardCompatibleUserPrincipal):
    """User model for API layer."""

    id: int  # User ID from database
    username: str
    role: str
    tenant_id: int  # Changed from str to int for database compatibility
    tenant_name: str  # Tenant display name
    timezone_iana: str | None = None
