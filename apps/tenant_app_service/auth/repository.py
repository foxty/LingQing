"""User repository."""

from datetime import UTC, datetime

import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.base_repository import BaseRepository
from apps.shared.db.models import TenantMembership, User, UserCredential
from apps.tenant_app_service.auth.domain import MembershipStatus, UserAccountStatus


class UserRepository(BaseRepository[User]):
    """Repository for User operations."""

    def __init__(self, db: AsyncSession):
        """Initialize user repository.

        Args:
            db: Database session
        """
        super().__init__(User, db)

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password using bcrypt.

        Args:
            password: Plain text password

        Returns:
            Hashed password
        """
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        """Verify password against hash.

        Args:
            password: Plain text password
            hashed: Hashed password

        Returns:
            True if password matches
        """
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))

    async def get_by_username_and_tenant(self, username: str, tenant_id: int) -> User | None:
        """Get user by username and tenant ID.

        Args:
            username: Username
            tenant_id: Tenant ID

        Returns:
            UserDomain or None if not found
        """
        result = await self.db.execute(
            select(User)
            .join(TenantMembership, TenantMembership.user_id == User.id)
            .where(
                User.username == username,
                TenantMembership.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_auth_record(
        self, username: str, tenant_id: int
    ) -> tuple[User, TenantMembership, UserCredential | None] | None:
        """Get auth record for username within tenant.

        Returns:
            Tuple of (User, TenantMembership, UserCredential | None) or None
        """
        result = await self.db.execute(
            select(User, TenantMembership, UserCredential)
            .join(TenantMembership, TenantMembership.user_id == User.id)
            .join(UserCredential, UserCredential.user_id == User.id, isouter=True)
            .where(
                User.username == username,
                TenantMembership.tenant_id == tenant_id,
            )
        )
        row = result.first()
        if not row:
            return None
        return row

    async def verify_password_for_user(self, user_id: int, password: str) -> bool:
        """Verify password for a specific user.

        This method is used for password change verification.
        Does not return user data, only validation result.

        Args:
            user_id: User ID
            password: Plain text password to verify

        Returns:
            True if password is correct, False otherwise
        """
        result = await self.db.execute(
            select(User, UserCredential)
            .join(UserCredential, UserCredential.user_id == User.id, isouter=True)
            .where(User.id == user_id)
        )
        row = result.first()
        if not row:
            return False

        db_user, credential = row
        password_hash = credential.password_hash if credential else db_user.hashed_password
        if not password_hash:
            return False

        return self.verify_password(password, password_hash)

    async def get_by_tenant(self, tenant_id: int) -> list[User]:
        """Get all users in a tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            List of UserDomain
        """
        result = await self.db.execute(
            select(User)
            .join(TenantMembership, TenantMembership.user_id == User.id)
            .where(TenantMembership.tenant_id == tenant_id)
        )
        return list(result.scalars().all())

    async def get_by_id_and_tenant(self, user_id: int, tenant_id: int) -> User | None:
        result = await self.db.execute(
            select(User)
            .join(TenantMembership, TenantMembership.user_id == User.id)
            .where(
                User.id == user_id,
                TenantMembership.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_user_membership(self, tenant_id: int, user_id: int) -> tuple[User, TenantMembership] | None:
        """Load a user and their tenant membership row."""
        result = await self.db.execute(
            select(User, TenantMembership)
            .join(TenantMembership, TenantMembership.user_id == User.id)
            .where(
                User.id == user_id,
                TenantMembership.tenant_id == tenant_id,
            )
        )
        return result.first()

    async def create_user(
        self, username: str, password: str, role: str, tenant_id: int, email: str | None = None
    ) -> User:
        """Create a new user with hashed password.

        Args:
            username: Username
            password: Plain text password (will be hashed)
            role: User role
            tenant_id: Tenant ID
            email: Email address

        Returns:
            Created UserDomain
        """
        password_hash = self.hash_password(password)
        user = User(
            username=username,
            hashed_password=password_hash,
            role=role,
            tenant_id=tenant_id,
            email=email.lower() if email else None,
            status=UserAccountStatus.ACTIVE,
        )
        db_user = await self.create(user)

        membership = TenantMembership(
            tenant_id=tenant_id,
            user_id=db_user.id,
            status=MembershipStatus.ACTIVE,
        )
        credential = UserCredential(
            user_id=db_user.id,
            password_hash=password_hash,
            password_updated_at=datetime.now(UTC),
            must_reset_password=False,
        )
        self.db.add(membership)
        self.db.add(credential)
        await self.db.flush()
        return db_user

    async def update_password(self, user_id: int, new_password: str) -> User | None:
        """Update user password.

        Args:
            user_id: User ID
            new_password: New plain text password (will be hashed)

        Returns:
            Updated UserDomain or None if not found
        """
        result = await self.db.execute(
            select(User, UserCredential)
            .join(UserCredential, UserCredential.user_id == User.id, isouter=True)
            .where(User.id == user_id)
        )
        row = result.first()
        if not row:
            return None

        user, credential = row
        password_hash = self.hash_password(new_password)
        user.hashed_password = password_hash

        if credential:
            credential.password_hash = password_hash
            credential.password_updated_at = datetime.now(UTC)
            credential.must_reset_password = False
        else:
            self.db.add(
                UserCredential(
                    user_id=user.id,
                    password_hash=password_hash,
                    password_updated_at=datetime.now(UTC),
                    must_reset_password=False,
                )
            )

        await self.db.flush()
        return user

    async def update_role(self, user_id: int, role: str) -> User | None:
        """Update user role.

        Args:
            user_id: User ID
            role: New role

        Returns:
            Updated UserDomain or None if not found
        """
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            return None

        user.role = role
        await self.db.flush()
        return user

    async def update_preferences(self, user_id: int, preferences_patch: dict) -> User | None:
        """Update user preferences with a shallow merge."""
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            return None

        current_preferences = user.preferences if isinstance(user.preferences, dict) else {}
        user.preferences = {
            **current_preferences,
            **preferences_patch,
        }
        await self.db.flush()
        return user

    async def update_last_login(self, user_id: int) -> User | None:
        """Update user's last login time.

        Args:
            user_id: User ID

        Returns:
            Updated UserDomain or None if not found
        """
        from datetime import datetime

        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            return None

        user.last_login_at = datetime.now(UTC)
        await self.db.flush()
        return user

    async def get_unique_username(self, tenant_id: int, base: str) -> str:
        """Find an available username within a tenant, uniquifying if needed."""
        base = base.strip().lower() or "user"
        candidate = base
        suffix = 1
        while True:
            result = await self.db.execute(
                select(User)
                .join(TenantMembership, TenantMembership.user_id == User.id)
                .where(
                    TenantMembership.tenant_id == tenant_id,
                    User.username == candidate,
                )
            )
            if result.scalar_one_or_none() is None:
                return candidate
            suffix += 1
            candidate = f"{base}{suffix}"

    async def create_jit_member(
        self,
        *,
        tenant_id: int,
        email: str | None,
        display_name: str | None,
        role: str = "viewer",
    ) -> User:
        """Create a user + active membership for JIT/SSO provisioning.

        Username is derived from the email local-part and uniquified within the
        tenant. A random unusable placeholder password is set so the account can
        only authenticate via SSO (or a later password-set flow).
        """
        import secrets

        base = (email or "").split("@", 1)[0] if email else "user"
        username = await self.get_unique_username(tenant_id, base)
        placeholder = "!" + secrets.token_urlsafe(32)
        user = User(
            username=username,
            hashed_password=placeholder,
            role=role,
            tenant_id=tenant_id,
            email=email.lower() if email else None,
            status="active",
        )
        self.db.add(user)
        await self.db.flush()
        membership = TenantMembership(
            tenant_id=tenant_id,
            user_id=user.id,
            status="active",
        )
        self.db.add(membership)
        await self.db.flush()
        return user
