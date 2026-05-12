"""Repository for dashboard data access (CRUD only)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.artifact.domain import ArtifactType
from apps.shared.artifact.mixins import ArtifactAwareMixin
from apps.shared.dashboard.adapters import db_dashboard_to_domain
from apps.shared.dashboard.domain import DashboardDomain
from apps.shared.db.base_repository import BaseRepository
from apps.shared.db.models import Dashboard, User


class DashboardRepository(ArtifactAwareMixin, BaseRepository[Dashboard]):
    """Repository for dashboards (tenant-scoped)."""

    def __init__(self, db: AsyncSession):
        super().__init__(Dashboard, db)
        self._artifact_type = ArtifactType.DASHBOARD
        self._entity_model = Dashboard
        self._session = db

    async def get_by_id_and_tenant(self, dashboard_id: int, tenant_id: int) -> DashboardDomain | None:
        result = await self.db.execute(
            select(Dashboard).where(
                Dashboard.id == dashboard_id,
                Dashboard.tenant_id == tenant_id,
            )
        )
        return db_dashboard_to_domain(result.scalar_one_or_none())

    async def get_by_tenant_and_name(self, tenant_id: int, name: str) -> DashboardDomain | None:
        result = await self.db.execute(
            select(Dashboard).where(
                Dashboard.tenant_id == tenant_id,
                Dashboard.name == name,
            )
        )
        return db_dashboard_to_domain(result.scalar_one_or_none())

    async def list_by_tenant(self, tenant_id: int) -> list[DashboardDomain]:
        result = await self.db.execute(
            select(Dashboard).where(Dashboard.tenant_id == tenant_id).order_by(Dashboard.updated_at.desc())
        )
        dashboards = result.scalars().all()
        return [db_dashboard_to_domain(d) for d in dashboards if d]

    async def list_for_tenant(self, tenant_id: int) -> list[DashboardDomain]:
        """All dashboards in the tenant (caller must have verified ``artifacts.manage``)."""
        stmt = self._build_list_stmt(
            tenant_id=tenant_id,
            configure=lambda stmt: stmt.order_by(Dashboard.updated_at.desc()),
            user_id=None,
        )
        stmt = stmt.join(User, User.id == Dashboard.owner_id, isouter=True).add_columns(User.username)
        result = await self.db.execute(stmt)
        rows = result.all()
        return [db_dashboard_to_domain(dashboard, owner_username=username) for dashboard, username in rows]

    async def list_for_user_access(self, *, tenant_id: int, user_id: int) -> list[DashboardDomain]:
        """Dashboards the user owns or has been shared via artifact shares."""
        stmt = self._build_list_stmt(
            tenant_id=tenant_id,
            user_id=user_id,
            configure=lambda stmt: stmt.order_by(Dashboard.updated_at.desc()),
        )
        stmt = stmt.join(User, User.id == Dashboard.owner_id, isouter=True).add_columns(User.username)
        result = await self.db.execute(stmt)
        rows = result.all()
        return [db_dashboard_to_domain(dashboard, owner_username=username) for dashboard, username in rows]

    async def create_dashboard(
        self,
        tenant_id: int,
        name: str,
        description: str | None,
        config: dict,
        owner_id: int,
    ) -> DashboardDomain:
        db_dashboard = Dashboard(
            tenant_id=tenant_id,
            name=name,
            description=description,
            config=config,
            owner_id=owner_id,
        )
        self.db.add(db_dashboard)
        await self.db.flush()
        await self.db.refresh(db_dashboard)
        return db_dashboard_to_domain(db_dashboard)

    async def update_fields(
        self,
        dashboard_id: int,
        tenant_id: int,
        name: str | None = None,
        description: str | None = None,
        config: dict | None = None,
    ) -> DashboardDomain | None:
        result = await self.db.execute(
            select(Dashboard).where(
                Dashboard.id == dashboard_id,
                Dashboard.tenant_id == tenant_id,
            )
        )
        db_dashboard = result.scalar_one_or_none()
        if not db_dashboard:
            return None

        if name is not None:
            db_dashboard.name = name
        if description is not None:
            db_dashboard.description = description
        if config is not None:
            db_dashboard.config = config

        await self.db.flush()
        await self.db.refresh(db_dashboard)
        return db_dashboard_to_domain(db_dashboard)

    async def delete_by_id_and_tenant(self, dashboard_id: int, tenant_id: int) -> bool:
        result = await self.db.execute(
            select(Dashboard).where(
                Dashboard.id == dashboard_id,
                Dashboard.tenant_id == tenant_id,
            )
        )
        db_dashboard = result.scalar_one_or_none()
        if not db_dashboard:
            return False

        await self.db.delete(db_dashboard)
        await self.db.flush()
        return True
