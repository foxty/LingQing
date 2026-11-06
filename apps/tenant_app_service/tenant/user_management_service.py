"""Tenant user management service.

Provides tenant-scoped user lifecycle operations for native identity.
"""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.authz.ta_rbac import DEFAULT_ROLE_PERMISSIONS
from apps.shared.core.base_service import TenantAwareService
from apps.shared.core.exceptions import DuplicateResourceError, ResourceNotFoundError, ValidationError
from apps.shared.db.models import TenantMembership, User
from apps.shared.utils.logger import get_logger
from apps.shared.utils.pagination import PaginationRequest
from apps.tenant_app_service.auth.domain import (
    MembershipStatus,
    UserRole,
    assert_tenant_retains_active_admin,
)
from apps.tenant_app_service.auth.repository import UserRepository
from apps.tenant_app_service.tenant.repository import TenantRepository
from apps.tenant_app_service.tenant.schemas import TenantUserDTO, TenantUserListResponse

logger = get_logger(__name__)


class TenantUserManagementService(TenantAwareService):
    """Service for tenant-scoped user management."""

    def __init__(self, tenant_id: int, db: AsyncSession):
        """Initialize user management service.

        Args:
            tenant_id: Tenant ID
            db: Database session
        """
        super().__init__(tenant_id=tenant_id, db_session=db)
        self.db = db
        self.tenant_repo = TenantRepository(db)
        self.user_repo = UserRepository(db)

    async def list_users(
        self,
        *,
        page: int = 1,
        page_size: int = 10,
        query: str | None = None,
    ) -> TenantUserListResponse:
        """List users within a tenant with optional search and pagination.

        Args:
            page: Page number (1-indexed)
            page_size: Page size (max 100 at router)
            query: Optional search by username substring or user id (numeric)

        Returns:
            Paginated list plus tenant-wide aggregates for admin UI.
        """
        tenant = await self.tenant_repo.get_by_id(self.tenant_id)
        if not tenant:
            raise ResourceNotFoundError("Tenant not found")

        total_tenant_members = await self.user_repo.count_tenant_memberships(self.tenant_id)
        active_admin_count = await self.user_repo.count_active_admins_in_tenant(self.tenant_id)
        total = await self.user_repo.count_users_in_tenant_filtered(self.tenant_id, query)

        if total == 0:
            return TenantUserListResponse(
                items=[],
                total=0,
                page=max(1, page),
                page_size=page_size,
                total_pages=0,
                total_tenant_members=total_tenant_members,
                active_admin_count=active_admin_count,
            )

        window = PaginationRequest.with_total(page=page, page_size=page_size, total=total)

        rows = await self.user_repo.list_users_in_tenant_page(
            self.tenant_id,
            offset=window.offset,
            limit=window.page_size,
            search_query=query,
        )
        items = [
            TenantUserDTO(
                id=user.id,
                username=user.username,
                role=user.role,
                tenant_id=self.tenant_id,
                tenant_name=tenant.name,
                membership_status=membership.status,
                is_break_glass=membership.is_break_glass,
            )
            for user, membership in rows
        ]

        return TenantUserListResponse(
            items=items,
            total=total,
            page=window.page,
            page_size=window.page_size,
            total_pages=window.total_pages,
            total_tenant_members=total_tenant_members,
            active_admin_count=active_admin_count,
        )

    async def create_user(
        self,
        username: str,
        password: str,
        role: str,
        email: str | None = None,
    ) -> TenantUserDTO:
        """Create a user within a tenant.

        Args:
            username: Username
            password: Plain text password
            role: User role
            email: Optional email

        Returns:
            TenantUserDTO
        """
        tenant = await self.tenant_repo.get_by_id(self.tenant_id)
        if not tenant:
            raise ResourceNotFoundError("Tenant not found")

        existing = await self.user_repo.get_by_username_and_tenant(username, self.tenant_id)
        if existing:
            raise DuplicateResourceError("User already exists in tenant")

        user = await self.user_repo.create_user(
            username=username,
            password=password,
            role=role,
            tenant_id=self.tenant_id,
            email=email,
        )

        logger.info(f"Created user {user.id} for tenant {self.tenant_id}")
        return TenantUserDTO(
            id=user.id,
            username=user.username,
            role=user.role,
            tenant_id=self.tenant_id,
            tenant_name=tenant.name,
            membership_status=MembershipStatus.ACTIVE,
        )

    async def _count_other_active_admins(self, exclude_user_id: int) -> int:
        result = await self.db.execute(
            select(func.count(User.id))
            .select_from(User)
            .join(TenantMembership, TenantMembership.user_id == User.id)
            .where(
                TenantMembership.tenant_id == self.tenant_id,
                TenantMembership.status == MembershipStatus.ACTIVE,
                User.role == UserRole.ADMIN,
                User.id != exclude_user_id,
            )
        )
        return result.scalar_one()

    async def deactivate_user(self, user_id: int, actor_user_id: int) -> None:
        """Deactivate a user's membership in a tenant.

        Args:
            user_id: User ID
            actor_user_id: Authenticated admin performing the action
        """
        if user_id == actor_user_id:
            raise ValidationError("Cannot deactivate your own account")

        result = await self.db.execute(
            select(User, TenantMembership)
            .join(TenantMembership, TenantMembership.user_id == User.id)
            .where(
                TenantMembership.tenant_id == self.tenant_id,
                User.id == user_id,
            )
        )
        row = result.first()
        if not row:
            raise ResourceNotFoundError("User membership not found")

        user, membership = row
        if membership.status == MembershipStatus.INACTIVE:
            return

        if user.role == UserRole.ADMIN:
            assert_tenant_retains_active_admin(
                role=user.role,
                other_active_admins=await self._count_other_active_admins(user.id),
            )

        membership.status = MembershipStatus.INACTIVE
        membership.deactivated_at = datetime.now(UTC)
        await self.db.flush()

        from apps.config import get_file_storage
        from apps.shared.document.sync_service import DocumentSyncService

        sync_service = DocumentSyncService(self.tenant_id, self.db, get_file_storage())
        await sync_service.deactivate_user_connections(owner_id=user_id)

        logger.info(f"Deactivated user {user_id} in tenant {self.tenant_id}")

    async def recover_user(self, user_id: int) -> None:
        """Recover (reactivate) a user's membership in a tenant.

        Args:
            user_id: User ID
        """
        result = await self.db.execute(
            select(TenantMembership).where(
                TenantMembership.tenant_id == self.tenant_id,
                TenantMembership.user_id == user_id,
            )
        )
        membership = result.scalar_one_or_none()
        if not membership:
            raise ResourceNotFoundError("User membership not found")

        if membership.status == MembershipStatus.INACTIVE:
            membership.status = MembershipStatus.ACTIVE
            membership.deactivated_at = None
            await self.db.flush()

        logger.info(f"Recovered user {user_id} in tenant {self.tenant_id}")

    async def reset_password(self, user_id: int, new_password: str) -> None:
        """Reset a user's password (admin action).

        Args:
            user_id: User ID
            new_password: New password
        """
        result = await self.db.execute(
            select(TenantMembership).where(
                TenantMembership.tenant_id == self.tenant_id,
                TenantMembership.user_id == user_id,
            )
        )
        membership = result.scalar_one_or_none()
        if not membership:
            raise ResourceNotFoundError("User membership not found")

        await self.user_repo.update_password(user_id, new_password)
        logger.info(f"Password reset for user {user_id} in tenant {self.tenant_id}")

    async def update_user_role(self, user_id: int, role: str, actor_user_id: int) -> TenantUserDTO:
        """Update a user's role in a tenant.

        Args:
            user_id: User ID
            role: New role

        Returns:
            Updated TenantUserDTO
        """
        if role not in DEFAULT_ROLE_PERMISSIONS:
            raise ValidationError(f"Role '{role}' not found")

        if user_id == actor_user_id:
            raise ValidationError("Cannot modify your own role")

        tenant = await self.tenant_repo.get_by_id(self.tenant_id)
        if not tenant:
            raise ResourceNotFoundError("Tenant not found")

        result = await self.db.execute(
            select(User, TenantMembership)
            .join(TenantMembership, TenantMembership.user_id == User.id)
            .where(
                TenantMembership.tenant_id == self.tenant_id,
                User.id == user_id,
            )
        )
        row = result.first()
        if not row:
            raise ResourceNotFoundError("User membership not found")

        user, membership = row

        if user.role == UserRole.ADMIN and role != UserRole.ADMIN:
            assert_tenant_retains_active_admin(
                role=user.role,
                other_active_admins=await self._count_other_active_admins(user.id),
            )

        updated = await self.user_repo.update_role(user.id, role)
        if not updated:
            raise ResourceNotFoundError("User not found")

        logger.info(f"Updated role for user {user_id} in tenant {self.tenant_id} to {role}")
        return TenantUserDTO(
            id=updated.id,
            username=updated.username,
            role=updated.role,
            tenant_id=self.tenant_id,
            tenant_name=tenant.name,
            membership_status=membership.status,
            is_break_glass=membership.is_break_glass,
        )
