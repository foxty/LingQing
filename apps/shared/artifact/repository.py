"""Repository for canonical artifacts, thread links, and sharing."""

from sqlalchemy import and_, delete, exists, func, not_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from apps.shared.db.models import AclGrant, Artifact, ArtifactLink, ResourceAcl
from apps.shared.domain.types import required_acl_permissions


class ArtifactRepository:
    """Data access layer for artifacts and artifact-thread links."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def link_artifact(
        self,
        thread_id: str | None,
        artifact_type: str,
        resource_id: int,
        tenant_id: int,
        owner_id: int,
        title: str | None = None,
        url: str | None = None,
        artifact_metadata: dict | None = None,
    ) -> Artifact:
        """Create/update artifact and optionally link it to a thread."""
        artifact = await self._get_or_create_artifact(
            tenant_id=tenant_id,
            owner_id=owner_id,
            artifact_type=artifact_type,
            resource_id=resource_id,
            source_thread_id=thread_id,
            title=title,
            url=url,
            artifact_metadata=artifact_metadata,
        )

        if thread_id:
            exists_stmt = select(ArtifactLink.id).where(
                ArtifactLink.artifact_id == artifact.id,
                ArtifactLink.thread_id == thread_id,
            )
            existing_link = (await self.db.execute(exists_stmt)).scalar_one_or_none()
            if existing_link is None:
                self.db.add(ArtifactLink(artifact_id=artifact.id, thread_id=thread_id))
                await self.db.flush()

        await self.db.refresh(artifact)
        return artifact

    async def list_linked_artifacts(
        self,
        thread_id: str,
        artifact_type: str | None = None,
    ) -> list[Artifact]:
        """Get artifacts linked to a thread."""
        stmt = (
            select(Artifact)
            .join(ArtifactLink, Artifact.id == ArtifactLink.artifact_id)
            .where(ArtifactLink.thread_id == thread_id)
            .options(joinedload(Artifact.owner_user))
        )
        if artifact_type:
            stmt = stmt.where(Artifact.artifact_type == artifact_type)
        stmt = stmt.order_by(Artifact.created_at.desc())

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    def _tenant_type_filters(self, tenant_id: int, artifact_type: str | None) -> list[object]:
        filters = [Artifact.tenant_id == tenant_id]
        if artifact_type:
            filters.append(Artifact.artifact_type == artifact_type)
        return filters

    async def _execute_artifact_list(
        self,
        *where_parts: object,
        limit: int,
        offset: int,
    ) -> list[Artifact]:
        stmt = (
            select(Artifact)
            .where(*where_parts)
            .options(joinedload(Artifact.owner_user))
            .order_by(Artifact.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_for_tenant(
        self,
        tenant_id: int,
        *,
        artifact_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Artifact]:
        """All artifacts in the tenant (caller must have verified ``artifacts.manage``)."""
        filters = self._tenant_type_filters(tenant_id, artifact_type)
        return await self._execute_artifact_list(*filters, limit=limit, offset=offset)

    async def list_for_user_access(
        self,
        tenant_id: int,
        user_id: int,
        *,
        artifact_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Artifact]:
        """Artifacts the user owns or can access via ACL grants."""
        filters = self._tenant_type_filters(tenant_id, artifact_type)
        allowed_permissions = required_acl_permissions("read")
        acl_allow_exists = exists(
            select(AclGrant.id)
            .join(
                ResourceAcl,
                and_(
                    ResourceAcl.tenant_id == AclGrant.tenant_id,
                    ResourceAcl.resource_type == AclGrant.resource_type,
                    ResourceAcl.resource_id == AclGrant.resource_id,
                ),
            )
            .where(
                AclGrant.tenant_id == tenant_id,
                AclGrant.resource_type == Artifact.artifact_type,
                AclGrant.resource_id == Artifact.resource_id,
                AclGrant.permission.in_(allowed_permissions),
                AclGrant.principal_type == "user",
                AclGrant.principal_id == str(user_id),
                AclGrant.effect == "allow",
                ResourceAcl.status == "active",
                not_(
                    exists(
                        select(AclGrant.id).where(
                            AclGrant.tenant_id == tenant_id,
                            AclGrant.resource_type == Artifact.artifact_type,
                            AclGrant.resource_id == Artifact.resource_id,
                            AclGrant.permission.in_(allowed_permissions),
                            AclGrant.principal_type == "user",
                            AclGrant.principal_id == str(user_id),
                            AclGrant.effect == "deny",
                        )
                    )
                ),
            )
        )
        access_filter = or_(
            Artifact.owner_id == user_id,
            acl_allow_exists,
        )
        return await self._execute_artifact_list(
            *filters,
            access_filter,
            limit=limit,
            offset=offset,
        )

    async def _ensure_resource_acl(self, *, artifact: Artifact, owner_id: int) -> None:
        stmt = select(ResourceAcl).where(
            ResourceAcl.tenant_id == artifact.tenant_id,
            ResourceAcl.resource_type == artifact.artifact_type,
            ResourceAcl.resource_id == artifact.resource_id,
        )
        resource_acl = (await self.db.execute(stmt)).scalar_one_or_none()
        if resource_acl is None:
            resource_acl = ResourceAcl(
                tenant_id=artifact.tenant_id,
                resource_type=artifact.artifact_type,
                resource_id=artifact.resource_id,
                owner_id=owner_id,
                status="active",
            )
            self.db.add(resource_acl)
            await self.db.flush()
            return
        if resource_acl.owner_id is None:
            resource_acl.owner_id = owner_id
        if resource_acl.status != "active":
            resource_acl.status = "active"
        await self.db.flush()

    async def get_by_id(self, artifact_id: int) -> Artifact | None:
        """Get artifact by Artifact ID."""
        stmt = select(Artifact).where(Artifact.id == artifact_id).options(joinedload(Artifact.owner_user))
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_resource(self, thread_id: str, artifact_type: str, resource_id: int) -> Artifact | None:
        """Get artifact associated with a specific thread and resource identity."""
        stmt = (
            select(Artifact)
            .where(
                Artifact.artifact_type == artifact_type,
                Artifact.resource_id == resource_id,
            )
            .join(ArtifactLink, Artifact.id == ArtifactLink.artifact_id)
            .where(ArtifactLink.thread_id == thread_id)
            .options(joinedload(Artifact.owner_user))
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def unlink_by_id(self, artifact_id: int, thread_id: str) -> bool:
        """Unlink artifact from thread by artifact ID."""
        stmt = delete(ArtifactLink).where(
            ArtifactLink.artifact_id == artifact_id,
            ArtifactLink.thread_id == thread_id,
        )
        result = await self.db.execute(stmt)
        await self.db.flush()
        return result.rowcount > 0

    async def unlink_artifact(self, thread_id: str, artifact_type: str, resource_id: int) -> bool:
        """Unlink artifact from thread by resource identity."""
        artifact_stmt = (
            select(Artifact.id)
            .where(
                Artifact.artifact_type == artifact_type,
                Artifact.resource_id == resource_id,
            )
            .join(ArtifactLink, Artifact.id == ArtifactLink.artifact_id)
            .where(ArtifactLink.thread_id == thread_id)
            .limit(1)
        )
        result = await self.db.execute(artifact_stmt)
        artifact_id = result.scalar_one_or_none()
        if not artifact_id:
            return False

        delete_stmt = delete(ArtifactLink).where(
            ArtifactLink.artifact_id == artifact_id,
            ArtifactLink.thread_id == thread_id,
        )
        delete_result = await self.db.execute(delete_stmt)
        await self.db.flush()
        return delete_result.rowcount > 0

    async def delete_all_by_resource(
        self,
        artifact_type: str,
        resource_id: int,
        tenant_id: int,
    ) -> int:
        """Delete canonical artifact rows for a given resource."""
        stmt = delete(Artifact).where(
            Artifact.artifact_type == artifact_type,
            Artifact.resource_id == resource_id,
            Artifact.tenant_id == tenant_id,
        )
        result = await self.db.execute(stmt)
        await self.db.flush()
        return result.rowcount

    async def count_linked_artifacts(self, thread_id: str) -> int:
        """Count artifacts linked to a thread."""
        stmt = select(func.count(ArtifactLink.id)).where(ArtifactLink.thread_id == thread_id)
        result = await self.db.execute(stmt)
        return int(result.scalar_one())

    async def _get_or_create_artifact(
        self,
        tenant_id: int,
        owner_id: int,
        artifact_type: str,
        resource_id: int,
        source_thread_id: str | None,
        title: str | None,
        url: str | None,
        artifact_metadata: dict | None,
    ) -> Artifact:
        stmt = select(Artifact).where(
            Artifact.tenant_id == tenant_id,
            Artifact.artifact_type == artifact_type,
            Artifact.resource_id == resource_id,
        )
        result = await self.db.execute(stmt)
        artifact = result.scalar_one_or_none()
        if artifact:
            if title is not None:
                artifact.title = title
            if url is not None:
                artifact.url = url
            if artifact_metadata is not None:
                artifact.artifact_metadata = artifact_metadata
            if artifact.source_thread_id is None and source_thread_id is not None:
                artifact.source_thread_id = source_thread_id
            if artifact.owner_id is None:
                artifact.owner_id = owner_id
            await self.db.flush()
            await self._ensure_resource_acl(
                artifact=artifact,
                owner_id=artifact.owner_id,
            )
            return artifact

        artifact = Artifact(
            tenant_id=tenant_id,
            owner_id=owner_id,
            source_thread_id=source_thread_id,
            artifact_type=artifact_type,
            resource_id=resource_id,
            title=title,
            url=url,
            artifact_metadata=artifact_metadata or {},
        )
        try:
            async with self.db.begin_nested():
                self.db.add(artifact)
                await self.db.flush()
        except IntegrityError:
            stmt = select(Artifact).where(
                Artifact.tenant_id == tenant_id,
                Artifact.artifact_type == artifact_type,
                Artifact.resource_id == resource_id,
            )
            result = await self.db.execute(stmt)
            artifact = result.scalar_one_or_none()
            if artifact is None:
                raise
            if title is not None:
                artifact.title = title
            if url is not None:
                artifact.url = url
            if artifact_metadata is not None:
                artifact.artifact_metadata = artifact_metadata
            if artifact.source_thread_id is None and source_thread_id is not None:
                artifact.source_thread_id = source_thread_id
            if artifact.owner_id is None:
                artifact.owner_id = owner_id
            await self.db.flush()
        await self._ensure_resource_acl(artifact=artifact, owner_id=owner_id)
        return artifact
