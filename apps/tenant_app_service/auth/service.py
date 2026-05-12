"""Authentication service."""

from datetime import UTC, datetime

from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from apps.config import get_settings
from apps.shared.core.exceptions import (
    AuthenticationError,
    ValidationError,
)
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.auth.adapters import db_auth_record_to_domain, db_user_to_domain, domain_user_to_api
from apps.tenant_app_service.auth.domain import TokenIssuer, UserDomain, UserPreferences, native_login_allowed
from apps.tenant_app_service.auth.password_validator import validate_password_complexity
from apps.tenant_app_service.auth.password_verifier import BcryptPasswordVerifier
from apps.tenant_app_service.auth.repository import UserRepository
from apps.tenant_app_service.auth.schemas import LoginRequest, LoginResponse
from apps.tenant_app_service.auth.token import JwtTokenIssuer
from apps.tenant_app_service.tenant.repository import TenantRepository

logger = get_logger(__name__)


class AuthService:
    """Service for handling authentication.

    Uses domain models for business rules and returns API DTOs.
    """

    def __init__(self, db: AsyncSession, token_issuer: TokenIssuer | None = None):
        """Initialize authentication service.

        Args:
            db: Database session
            token_issuer: Token issuer port (defaults to JwtTokenIssuer)
        """
        self.settings = get_settings()
        self.db = db
        self.user_repo = UserRepository(db)
        self.tenant_repo = TenantRepository(db)
        self.token_issuer = token_issuer or JwtTokenIssuer(self.settings)

    async def authenticate(self, credentials: LoginRequest) -> LoginResponse:
        """Authenticate user and return JWT token.

        Login format: username@slug (e.g., "admin@demo")
        - Uses rsplit("@", 1) to support usernames with @ symbols
        - Example: "user@email.com@demo" → username="user@email.com", slug="demo"

        Args:
            credentials: Login credentials (username must include @slug)

        Returns:
            LoginResponse with access token and user info

        Raises:
            AuthenticationError: If authentication fails
            ValidationError: If credentials format is invalid
        """
        identity, tenant = await self._resolve_tenant_and_identity(
            credentials.username,
            error_on_missing="Invalid username or password",
        )

        logger.info(f"Login attempt: {identity}@{tenant.slug}")

        # Load auth record for status + password checks
        auth_record = await self.user_repo.get_auth_record(identity, tenant.id)
        if not auth_record:
            raise ValidationError("用户名或密码错误", {"code": "AUTH_INVALID_CREDENTIALS"})

        db_user, membership, credential = auth_record

        # Force SSO: native password login is rejected unless break-glass.
        # `force_sso` is a tenant property; auth reads it off the tenant row with
        # no SSO module dependency.
        if not native_login_allowed(
            force_sso=getattr(tenant, "force_sso", False),
            is_break_glass=getattr(membership, "is_break_glass", False),
        ):
            raise ValidationError(
                "Password login is disabled for this tenant; use SSO",
                {"code": "AUTH_SSO_REQUIRED"},
            )

        auth_domain = db_auth_record_to_domain(db_user, membership, credential)
        verifier = BcryptPasswordVerifier()
        user = auth_domain.authenticate(credentials.password, verifier)

        # Create JWT token
        access_token = self.token_issuer.issue(
            user_id=user.id,
            username=user.username,
            role=user.role,
            tenant_id=tenant.id,
            tenant_name=tenant.name,
        )

        # Update last login time
        await self.user_repo.update_last_login(user.id)
        await self.db.commit()

        logger.info(f"User {identity} logged in successfully (tenant: {tenant.name})")

        # Return domain model
        return LoginResponse(
            access_token=access_token,
            token_type="bearer",
            user=domain_user_to_api(user, tenant_name=tenant.name),
        )

    async def _resolve_tenant_and_identity(self, identifier: str, error_on_missing: str):
        """Resolve tenant and return identity + tenant.

        Supported formats:
        - username@slug
        - user@domain.com (pure email): currently not supported

        Returns:
            Tuple of (user_identity, tenant)
        """
        if "@" not in identifier:
            raise ValidationError(
                "请输入邮箱或账号@租户标识",
                {"code": "AUTH_IDENTIFIER_INVALID"},
            )

        user_identity, tenant_part = identifier.rsplit("@", 1)
        if not user_identity or not tenant_part:
            raise ValidationError(
                "请输入邮箱或账号@租户标识",
                {"code": "AUTH_IDENTIFIER_INVALID"},
            )

        # Pure email (user@domain.com) is not supported yet.
        if "." in tenant_part:
            raise ValidationError(
                "暂不支持使用邮箱登录，请使用 账号@租户标识",
                {"code": "AUTH_EMAIL_NOT_SUPPORTED"},
            )

        tenant = await self.tenant_repo.get_by_slug(tenant_part)
        if not tenant:
            raise ValidationError(error_on_missing, {"code": "AUTH_TENANT_NOT_FOUND"})
        return user_identity, tenant

    def verify_token(self, token: str) -> UserDomain:
        """Verify JWT token and return user information.

        Args:
            token: JWT token string

        Returns:
            UserDomain with user info

        Raises:
            AuthenticationError: If token is invalid or expired
        """
        try:
            payload = jwt.decode(token, self.settings.SECRET_KEY, algorithms=[self.settings.ALGORITHM])
            user_id: int = payload.get("user_id")
            username: str = payload.get("sub")
            role: str = payload.get("role")
            tenant_id: int = payload.get("tenant_id")  # Integer
            tenant_name: str = payload.get("tenant_name")  # Display name

            if user_id is None or username is None or role is None or tenant_id is None or tenant_name is None:
                raise AuthenticationError("Invalid token payload")

            # Return UserDomain (Note: missing some fields like created_at, so this is partial)
            return UserDomain(
                id=user_id,
                username=username,
                email=None,
                role=role,
                tenant_id=tenant_id,
                status="active",  # Assumed from valid token
                preferences=UserPreferences(),
                created_at=datetime.now(UTC),  # Placeholder
                updated_at=datetime.now(UTC),  # Placeholder
                last_login_at=None,
            )

        except JWTError as e:
            logger.warning(f"Token verification failed: {e}")
            raise AuthenticationError("Could not validate credentials")

    async def get_user_profile(self, user_id: int) -> UserDomain:
        """Get user profile by user ID.

        Args:
            user_id: User ID

        Returns:
            UserDomain with complete user information

        Raises:
            AuthenticationError: If user not found
        """
        user_repo = UserRepository(self.db)
        db_user = await user_repo.get_by_id(user_id)

        if not db_user:
            raise ValidationError("User not found")

        return db_user_to_domain(db_user)

    async def change_password(self, user_id: int, old_password: str, new_password: str) -> None:
        """Change user password.

        Args:
            user_id: User ID
            old_password: Current password for verification
            new_password: New password to set

        Raises:
            AuthenticationError: If old password is incorrect
            ValidationError: If new password doesn't meet requirements
        """
        user_repo = UserRepository(self.db)

        # Get user - need to verify old password using internal DB password hash
        # Since UserDomain doesn't expose hashed_password, we need repository method
        is_valid = await user_repo.verify_password_for_user(user_id, old_password)
        if not is_valid:
            raise ValidationError("Current password is incorrect")

        # Validate new password complexity (business rule)
        validate_password_complexity(new_password)

        # Update password
        await user_repo.update_password(user_id, new_password)
        await self.db.commit()

        # Get user for logging
        user = await user_repo.get_by_id(user_id)
        logger.info(f"Password changed successfully for user {user.username} (ID: {user_id})")

    async def update_profile_preferences(self, user_id: int, timezone_iana: str | None) -> UserDomain:
        """Update user profile preferences."""
        user_repo = UserRepository(self.db)
        updated = await user_repo.update_preferences(
            user_id=user_id,
            preferences_patch={"timezone_iana": timezone_iana},
        )
        if not updated:
            raise ValidationError("User not found")
        await self.db.commit()
        return db_user_to_domain(updated)

    async def accept_invite(self, token: str, password: str) -> LoginResponse:
        """Accept invite and set password (Phase 0 stub)."""
        raise ValidationError("Invite flow not implemented yet")

    async def reset_password_with_token(self, token: str, new_password: str) -> None:
        """Reset password with token (Phase 0 stub)."""
        raise ValidationError("Reset password flow not implemented yet")
