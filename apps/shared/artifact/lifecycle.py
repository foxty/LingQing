"""Composable helper for artifact-backed entity lifecycle operations."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.artifact.domain import ArtifactType
from apps.shared.artifact.repository import ArtifactRepository
from apps.shared.db.models import Artifact


class ArtifactLifecycle:
    """Shared artifact lifecycle for entity services."""

    def __init__(
        self,
        *,
        db: AsyncSession,
        tenant_id: int,
        artifact_type: ArtifactType,
        entity_repo: Any,
    ):
        self._artifact_repo = ArtifactRepository(db)
        self._tenant_id = tenant_id
        self._artifact_type = artifact_type
        self._entity_repo = entity_repo

    async def link_on_create(
        self,
        *,
        resource_id: int,
        owner_id: int,
        title: str | None = None,
        url: str | None = None,
        thread_id: str | None = None,
        metadata: dict | None = None,
    ) -> Artifact:
        return await self._artifact_repo.link_artifact(
            thread_id=thread_id,
            artifact_type=self._artifact_type.value,
            resource_id=resource_id,
            tenant_id=self._tenant_id,
            owner_id=owner_id,
            title=title,
            url=url,
            artifact_metadata=metadata,
        )

    async def list_entities(
        self,
        *,
        user_id: int,
        has_manage: bool,
        **kwargs,
    ) -> list[Any]:
        if has_manage:
            return await self._entity_repo.list_for_tenant(tenant_id=self._tenant_id, **kwargs)
        return await self._entity_repo.list_for_user_access(
            tenant_id=self._tenant_id,
            user_id=user_id,
            **kwargs,
        )

    async def delete_cascade(self, *, resource_id: int) -> int:
        return await self._artifact_repo.delete_all_by_resource(
            artifact_type=self._artifact_type.value,
            resource_id=resource_id,
            tenant_id=self._tenant_id,
        )
