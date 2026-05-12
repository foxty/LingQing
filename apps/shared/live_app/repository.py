"""Repository utilities for live apps."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.shared.artifact.domain import ArtifactType
from apps.shared.artifact.mixins import ArtifactAwareMixin
from apps.shared.db.models import LiveApp


class LiveAppRepository(ArtifactAwareMixin):
    """Data access for live app records."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.model = LiveApp
        self._artifact_type = ArtifactType.APP
        self._entity_model = LiveApp
        self._session = db

    async def get_for_tenant(self, app_id: int, tenant_id: int) -> LiveApp | None:
        stmt = (
            select(LiveApp)
            .options(selectinload(LiveApp.owner_user))
            .where(LiveApp.id == app_id, LiveApp.tenant_id == tenant_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_for_tenant(self, *, app_id: int, tenant_id: int) -> bool:
        live_app = await self.get_for_tenant(app_id=app_id, tenant_id=tenant_id)
        if live_app is None:
            return False
        await self.db.delete(live_app)
        await self.db.flush()
        return True

    async def list_for_tenant(self, tenant_id: int) -> list[LiveApp]:
        return await self._list_entities(
            tenant_id=tenant_id,
            user_id=None,
            configure=lambda stmt: stmt.options(selectinload(LiveApp.owner_user)).order_by(
                LiveApp.updated_at.desc(), LiveApp.id.desc()
            ),
        )

    async def list_for_user_access(self, *, tenant_id: int, user_id: int) -> list[LiveApp]:
        """List live apps a user can read: owner or shared via artifact shares."""
        return await self._list_entities(
            tenant_id=tenant_id,
            user_id=user_id,
            configure=lambda stmt: stmt.options(selectinload(LiveApp.owner_user)).order_by(
                LiveApp.updated_at.desc(), LiveApp.id.desc()
            ),
        )

    async def add(
        self,
        *,
        tenant_id: int,
        owner_id: int,
        name: str,
        description: str | None = None,
        entry_file: str = "entry.html",
        sdk_version: str = "1.0",
        app_config: dict | None = None,
        data_source_id: int | None = None,
    ) -> LiveApp:
        live_app = LiveApp(
            tenant_id=tenant_id,
            owner_id=owner_id,
            data_source_id=data_source_id,
            name=name,
            description=description,
            entry_file=entry_file,
            sdk_version=sdk_version,
            app_config=app_config or {},
        )
        self.db.add(live_app)
        await self.db.flush()
        await self.db.refresh(live_app)
        return live_app
