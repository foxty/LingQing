"""Local auth service for tenant manager native users."""

from datetime import UTC, datetime, timedelta

import bcrypt
from jose import jwt

from apps.config import get_settings
from apps.shared.authz.tm_rbac import PLATFORM_ROLES
from apps.shared.core.exceptions import (
    AuthenticationError,
    DuplicateResourceError,
    ResourceNotFoundError,
    ValidationError,
)
from apps.tenant_manager_service.repositories.user_repository import TenantManagerUserRepository


class TMLocalUserService:
    """Native identity service for control-plane users."""

    def __init__(self, repository: TenantManagerUserRepository):
        self.repository = repository
        self.settings = get_settings()

    async def create_user(self, username: str, display_name: str, password: str, role: str):
        if role not in PLATFORM_ROLES:
            raise ValidationError("Invalid platform role", {"role": role})

        existing = await self.repository.get_by_username(username)
        if existing:
            raise DuplicateResourceError("Username already exists", {"username": username})

        password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        return await self.repository.create_user(
            username=username,
            display_name=display_name,
            password_hash=password_hash,
            role=role,
        )

    async def bootstrap_admin(self, username: str, display_name: str, password: str):
        total_users = await self.repository.count_users()
        if total_users > 0:
            raise ValidationError("Bootstrap is only allowed when no users exist")
        return await self.create_user(
            username=username,
            display_name=display_name,
            password=password,
            role="platform_admin",
        )

    async def list_users(self):
        return await self.repository.list_users()

    async def get_user(self, user_id: int):
        user = await self.repository.get_by_id(user_id)
        if not user:
            raise ResourceNotFoundError("Tenant manager user not found", {"user_id": user_id})
        return user

    async def update_user_status(self, user_id: int, status: str):
        if status not in {"active", "inactive"}:
            raise ValidationError("Invalid user status", {"status": status})

        user = await self.repository.get_by_id(user_id)
        if not user:
            raise ResourceNotFoundError("Tenant manager user not found", {"user_id": user_id})

        return await self.repository.update_status(user, status)

    async def login(self, username: str, password: str):
        user = await self.repository.get_by_username(username)
        if not user:
            raise AuthenticationError("Invalid username or password")
        if user.status != "active":
            raise AuthenticationError("User is inactive")

        valid_password = bcrypt.checkpw(password.encode("utf-8"), user.password_hash.encode("utf-8"))
        if not valid_password:
            raise AuthenticationError("Invalid username or password")

        token = self._create_access_token(user.id, user.username, user.role)
        return token, user

    def _create_access_token(self, user_id: int, username: str, role: str) -> str:
        expires = datetime.now(UTC) + timedelta(minutes=self.settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        payload = {
            "sub": username,
            "user_id": user_id,
            "role": role,
            "provider": "native",
            "scope": "tenant-manager",
            "exp": expires,
        }
        return jwt.encode(payload, self.settings.SECRET_KEY, algorithm=self.settings.ALGORITHM)
