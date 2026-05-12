"""Reusable repository mixin for artifact-aware list queries."""

from collections.abc import Callable
from typing import Any

from sqlalchemy import and_, exists, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from apps.shared.artifact.domain import ArtifactType
from apps.shared.db.models import AclGrant, Artifact, ResourceAcl
from apps.shared.domain.types import required_acl_permissions


class ArtifactAwareMixin:
    """Add shared tenant/user-access list behavior for artifact-backed entities.

    Repository contract:
    - ``_entity_model``: SQLAlchemy model class (e.g. Dashboard, Report, LiveApp)
    - ``_session``: Async SQLAlchemy session used to execute statements
    - ``_artifact_type``: ArtifactType enum value for this entity
    - ``_owner_column``: owner field name on entity model (default: ``owner_id``)

        Access model implemented by this mixin:
    - Tenant-wide list: rows filtered only by ``entity.tenant_id``
    - User-access list: rows filtered by one of:
      1) entity owner match (owner column == user_id)
            2) artifact owner match (Artifact.owner_id == user_id)
            3) explicit ACL allow grant (AclGrant principal=user) with deny precedence

    This centralizes the repeated owner/share SQL pattern across repositories.
    """

    _artifact_type: ArtifactType
    _entity_model: Any
    _session: AsyncSession
    _owner_column: str = "owner_id"

    def _build_list_stmt(
        self,
        *,
        tenant_id: int,
        user_id: int | None,
        configure: Callable[[Select[Any]], Select[Any]],
    ) -> Select[Any]:
        """Build a base select for entity listing with optional access controls.

        Args:
            tenant_id: Required tenant scope. Always applied.
            user_id:
                - ``None``: no user-level access filter (tenant-wide listing)
                - ``int``: apply owner/share access filters for that user
            configure: Callback to apply repository-specific concerns
                (ordering, pagination, joinedload, extra filters).
        """
        entity = self._entity_model
        stmt = select(entity).where(entity.tenant_id == tenant_id)

        if user_id is not None:
            # Direct owner rule on entity table.
            owner_column = getattr(entity, self._owner_column)
            # Artifact owner rule is based on unified owner_id.
            owner_artifact_exists = (
                select(Artifact.id)
                .where(
                    Artifact.tenant_id == tenant_id,
                    Artifact.artifact_type == self._artifact_type.value,
                    Artifact.resource_id == entity.id,
                    Artifact.owner_id == user_id,
                )
                .exists()
            )
            required_permissions = required_acl_permissions("read")
            # ACL rule: user has an explicit allow grant without a matching deny.
            shared_exists = exists(
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
                    AclGrant.resource_type == self._artifact_type.value,
                    AclGrant.resource_id == entity.id,
                    AclGrant.principal_type == "user",
                    AclGrant.principal_id == str(user_id),
                    AclGrant.permission.in_(required_permissions),
                    AclGrant.effect == "allow",
                    ResourceAcl.status == "active",
                    not_(
                        exists(
                            select(AclGrant.id).where(
                                AclGrant.tenant_id == tenant_id,
                                AclGrant.resource_type == self._artifact_type.value,
                                AclGrant.resource_id == entity.id,
                                AclGrant.principal_type == "user",
                                AclGrant.principal_id == str(user_id),
                                AclGrant.permission.in_(required_permissions),
                                AclGrant.effect == "deny",
                            )
                        )
                    ),
                )
            )
            stmt = stmt.where(
                or_(
                    owner_column == user_id,
                    owner_artifact_exists,
                    shared_exists,
                )
            )

        # Let each repository add ordering/pagination/eager-load details.
        return configure(stmt)

    async def _list_entities(
        self,
        *,
        tenant_id: int,
        user_id: int | None,
        configure: Callable[[Select[Any]], Select[Any]],
        mapper: Callable[[Any], Any] | None = None,
    ) -> list[Any]:
        """Execute the built statement and optionally map DB rows to domain DTOs.

        ``mapper`` is optional so repos can choose return shape:
        - raw ORM models (mapper=None)
        - domain objects / DTOs (mapper=db_to_domain_adapter)
        """
        stmt = self._build_list_stmt(tenant_id=tenant_id, user_id=user_id, configure=configure)
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        if mapper is None:
            return rows
        return [mapper(row) for row in rows]
