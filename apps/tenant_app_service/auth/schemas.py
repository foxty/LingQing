"""DTOs for auth module.

Note: User model moved to apps.shared.schemas.user
Import from there: from apps.shared.schemas.user import UserDTO
"""

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator

from apps.shared.schemas.user import UserDTO


class LoginRequest(BaseModel):
    """Login request model.

    Username format: username@tenant-slug
    Example: "admin@demo"

    For usernames with @ symbols (like emails), append @slug:
    Example: "user@email.com@demo"
    """

    username: str = Field(..., description="Username in format: username@tenant-slug")
    password: str


class LoginResponse(BaseModel):
    """Login response model."""

    access_token: str
    token_type: str
    user: UserDTO


class ProfilePreferences(BaseModel):
    """Supported user preferences."""

    timezone_iana: str | None = None


class ProfileResponse(BaseModel):
    """User profile response model."""

    id: int
    username: str
    email: str | None
    role: str
    tenant_id: int
    tenant_name: str
    status: str
    last_login_at: str | None
    created_at: str
    updated_at: str
    permissions: list[str]
    preferences: ProfilePreferences


class UpdateProfilePreferencesRequest(BaseModel):
    """Profile preference update payload."""

    timezone_iana: str | None = None

    @field_validator("timezone_iana")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        candidate = value.strip()
        if not candidate:
            raise ValueError("timezone cannot be empty")
        try:
            ZoneInfo(candidate)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        return candidate


class ChangePasswordRequest(BaseModel):
    """Change password request model."""

    old_password: str = Field(..., description="Current password for verification")
    new_password: str = Field(
        ...,
        min_length=8,
        description="New password (minimum 8 characters, must contain uppercase, lowercase, and number)",
    )
    confirm_password: str = Field(..., description="Confirm new password")


class InviteAcceptRequest(BaseModel):
    """Accept invite request model."""

    token: str = Field(..., description="Invite token")
    password: str = Field(..., description="New password")


class InviteAcceptResponse(BaseModel):
    """Accept invite response model."""

    access_token: str
    token_type: str
    user: UserDTO


class ResetPasswordRequest(BaseModel):
    """Reset password request model."""

    token: str = Field(..., description="Reset token")
    new_password: str = Field(..., description="New password")
