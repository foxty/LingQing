"""Adapters for User/Auth domain model conversions."""

from datetime import UTC, datetime

from apps.shared.db import models as db_models
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.auth.domain import UserAuthDomain, UserDomain, UserPreferences
from apps.tenant_app_service.auth.schemas import (
    ProfilePreferences,
    ProfileResponse,
)

# ============ DB Conversions ============


def db_user_to_domain(db_user: db_models.User) -> UserDomain:
    """Convert DB User to Domain User."""
    return UserDomain(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        role=db_user.role,
        tenant_id=db_user.tenant_id,
        status=db_user.status,
        preferences=UserPreferences.from_raw(db_user.preferences),
        last_login_at=db_user.last_login_at,
        created_at=db_user.created_at,
        updated_at=db_user.updated_at,
    )


# ============ API Conversions ============


def api_user_to_domain(api_user: UserDTO) -> UserDomain:
    """Convert API User to Domain User.

    Note: API User doesn't have all fields, this is a partial conversion.
    Used when we need to pass user context from auth to services.
    """
    # API User is minimal, create domain user with required fields
    return UserDomain(
        id=api_user.id,
        username=api_user.username,
        email=api_user.email or "",
        role=api_user.role,
        tenant_id=api_user.tenant_id,
        status="active",  # Assume active if coming from API
        preferences=UserPreferences(timezone_iana=api_user.timezone_iana),
        last_login_at=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def domain_user_to_api(domain_user: UserDomain, tenant_name: str) -> UserDTO:
    """Convert Domain User to API User."""
    return UserDTO(
        id=domain_user.id,
        username=domain_user.username,
        email=domain_user.email,
        role=domain_user.role,
        tenant_id=domain_user.tenant_id,
        tenant_name=tenant_name,
        timezone_iana=domain_user.preferences.timezone_iana,
    )


async def domain_user_to_profile_response(
    domain_user: UserDomain, tenant_name: str, permissions: list[str]
) -> ProfileResponse:
    """Convert Domain User to API ProfileResponse.

    Args:
        domain_user: User domain model
        tenant_name: Tenant name
        permissions: List of effective permissions for the user

    Returns:
        ProfileResponse with user info and permissions
    """
    return ProfileResponse(
        id=domain_user.id,
        username=domain_user.username,
        email=domain_user.email,
        role=domain_user.role,
        tenant_id=domain_user.tenant_id,
        tenant_name=tenant_name,
        status=domain_user.status,
        last_login_at=domain_user.last_login_at.isoformat() if domain_user.last_login_at else None,
        created_at=domain_user.created_at.isoformat(),
        updated_at=domain_user.updated_at.isoformat(),
        permissions=permissions,
        preferences=ProfilePreferences(timezone_iana=domain_user.preferences.timezone_iana),
    )


def db_auth_record_to_domain(
    db_user: db_models.User,
    membership: db_models.TenantMembership,
    credential: db_models.UserCredential | None,
) -> UserAuthDomain:
    """Convert auth record DB models to UserAuthDomain."""
    password_hash = credential.password_hash if credential else db_user.hashed_password
    return UserAuthDomain(
        user=db_user_to_domain(db_user),
        membership_status=membership.status,
        password_hash=password_hash,
    )
