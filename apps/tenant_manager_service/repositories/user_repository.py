"""Repository for tenant manager local users."""

from datetime import UTC, datetime

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.tenant_manager_service.db.models import TenantManagerUser


class TenantManagerUserRepository:
    """Persistence for local control-plane users."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_username(self, username: str) -> TenantManagerUser | None:
        result = await self.db.execute(select(TenantManagerUser).where(TenantManagerUser.username == username))
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> TenantManagerUser | None:
        result = await self.db.execute(select(TenantManagerUser).where(TenantManagerUser.id == user_id))
        return result.scalar_one_or_none()

    async def list_users(self) -> list[TenantManagerUser]:
        result = await self.db.execute(select(TenantManagerUser).order_by(desc(TenantManagerUser.updated_at)))
        return list(result.scalars().all())

    async def create_user(
        self,
        username: str,
        display_name: str,
        password_hash: str,
        role: str,
    ) -> TenantManagerUser:
        user = TenantManagerUser(
            username=username,
            display_name=display_name,
            password_hash=password_hash,
            role=role,
            status="active",
        )
        self.db.add(user)
        await self.db.flush()
        return user

    async def count_users(self) -> int:
        result = await self.db.execute(select(func.count(TenantManagerUser.id)))
        return int(result.scalar() or 0)

    async def update_status(self, user: TenantManagerUser, status: str) -> TenantManagerUser:
        user.status = status
        user.updated_at = datetime.now(UTC)
        await self.db.flush()
        return user
