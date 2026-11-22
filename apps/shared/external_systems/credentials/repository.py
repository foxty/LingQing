"""Persistence for user_integration_credentials."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select

from apps.shared.db.base_repository import BaseRepository
from apps.shared.db.models import User, UserIntegrationCredential
from apps.shared.external_systems.credentials.domain import CREDENTIAL_STATUS_ACTIVE, CREDENTIAL_STATUS_REVOKED

_PROVISIONED_UNSET = object()


class UserIntegrationCredentialRepository(BaseRepository[UserIntegrationCredential]):
    def __init__(self, db_session):
        super().__init__(UserIntegrationCredential, db_session)

    async def get_binding(
        self,
        *,
        tenant_id: int,
        user_id: int,
        resource_type: str,
        resource_id: int,
    ) -> UserIntegrationCredential | None:
        result = await self.db.execute(
            select(UserIntegrationCredential).where(
                UserIntegrationCredential.tenant_id == tenant_id,
                UserIntegrationCredential.user_id == user_id,
                UserIntegrationCredential.resource_type == resource_type,
                UserIntegrationCredential.resource_id == resource_id,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_binding(
        self,
        *,
        tenant_id: int,
        user_id: int,
        resource_type: str,
        resource_id: int,
        auth_type: str,
        secrets_enc: dict,
        account_label: str | None,
        status: str = CREDENTIAL_STATUS_ACTIVE,
        expires_at: datetime | None = None,
        provisioned_by_user_id: int | None = _PROVISIONED_UNSET,
        provisioned_at: datetime | None = _PROVISIONED_UNSET,
    ) -> UserIntegrationCredential:
        existing = await self.get_binding(
            tenant_id=tenant_id,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        now = datetime.now(UTC)
        if existing:
            existing.auth_type = auth_type
            existing.secrets_enc = secrets_enc
            existing.account_label = account_label
            existing.status = status
            existing.expires_at = expires_at
            if provisioned_by_user_id is not _PROVISIONED_UNSET:
                existing.provisioned_by_user_id = provisioned_by_user_id
            if provisioned_at is not _PROVISIONED_UNSET:
                existing.provisioned_at = provisioned_at
            existing.updated_at = now
            await self.db.flush()
            return existing

        row = UserIntegrationCredential(
            tenant_id=tenant_id,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            auth_type=auth_type,
            secrets_enc=secrets_enc,
            account_label=account_label,
            status=status,
            expires_at=expires_at,
            provisioned_by_user_id=(
                None if provisioned_by_user_id is _PROVISIONED_UNSET else provisioned_by_user_id
            ),
            provisioned_at=None if provisioned_at is _PROVISIONED_UNSET else provisioned_at,
            created_at=now,
            updated_at=now,
        )
        return await self.create(row)

    async def revoke_binding(
        self,
        *,
        tenant_id: int,
        user_id: int,
        resource_type: str,
        resource_id: int,
    ) -> bool:
        row = await self.get_binding(
            tenant_id=tenant_id,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        if row is None:
            return False
        row.status = CREDENTIAL_STATUS_REVOKED
        row.updated_at = datetime.now(UTC)
        await self.db.flush()
        return True

    async def delete_binding(
        self,
        *,
        tenant_id: int,
        user_id: int,
        resource_type: str,
        resource_id: int,
    ) -> bool:
        row = await self.get_binding(
            tenant_id=tenant_id,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        if row is None:
            return False
        await self.db.delete(row)
        await self.db.flush()
        return True

    async def count_active_bindings(
        self,
        *,
        tenant_id: int,
        resource_type: str,
        resource_id: int,
    ) -> int:
        result = await self.db.execute(
            select(func.count())
            .select_from(UserIntegrationCredential)
            .where(
                UserIntegrationCredential.tenant_id == tenant_id,
                UserIntegrationCredential.resource_type == resource_type,
                UserIntegrationCredential.resource_id == resource_id,
                UserIntegrationCredential.status == CREDENTIAL_STATUS_ACTIVE,
            )
        )
        return int(result.scalar_one())

    async def list_bindings_for_resource(
        self,
        *,
        tenant_id: int,
        resource_type: str,
        resource_id: int,
    ) -> list[tuple[UserIntegrationCredential, User]]:
        result = await self.db.execute(
            select(UserIntegrationCredential, User)
            .join(User, User.id == UserIntegrationCredential.user_id)
            .where(
                UserIntegrationCredential.tenant_id == tenant_id,
                UserIntegrationCredential.resource_type == resource_type,
                UserIntegrationCredential.resource_id == resource_id,
            )
            .order_by(User.username.asc())
        )
        return list(result.all())

    async def list_bindings_for_user(
        self,
        *,
        tenant_id: int,
        user_id: int,
        resource_type: str | None = None,
    ) -> list[UserIntegrationCredential]:
        stmt = (
            select(UserIntegrationCredential)
            .where(
                UserIntegrationCredential.tenant_id == tenant_id,
                UserIntegrationCredential.user_id == user_id,
            )
            .order_by(
                UserIntegrationCredential.resource_type.asc(),
                UserIntegrationCredential.resource_id.asc(),
            )
        )
        if resource_type is not None:
            stmt = stmt.where(UserIntegrationCredential.resource_type == resource_type)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
