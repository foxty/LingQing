"""Tenant-scoped repository for SSO tables.

All queries are scoped by tenant_id. Secrets are encrypted via FieldCipher
on write and decrypted on read inside the service layer.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import (
    AuthProvider,
    SsoLoginState,
    SsoLoginTicket,
    Tenant,
)
from apps.shared.external_identity.repository import ExternalIdentityRepository
from apps.shared.utils.field_cipher import FieldCipher

_CLIENT_SECRET_FIELDS = {"client_secret"}


class SsoRepository:
    """Repository for SSO tables.

    Covers auth_providers, tenant_login_domains, external_identities,
    sso_login_states, sso_login_tickets. All tenant-scoped.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self._cipher = FieldCipher()
        self._identity_repo = ExternalIdentityRepository(db)

    # ---------- Provider config ----------

    async def list_providers(self, tenant_id: int) -> list[AuthProvider]:
        result = await self.db.execute(
            select(AuthProvider).where(
                AuthProvider.tenant_id == tenant_id,
                AuthProvider.provider_type == "oidc",
            )
        )
        return list(result.scalars().all())

    async def get_provider(self, tenant_id: int, provider_id: int) -> AuthProvider | None:
        result = await self.db.execute(
            select(AuthProvider).where(
                AuthProvider.tenant_id == tenant_id,
                AuthProvider.id == provider_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_provider_by_name(self, tenant_id: int, display_name: str) -> AuthProvider | None:
        result = await self.db.execute(
            select(AuthProvider).where(
                AuthProvider.tenant_id == tenant_id,
                AuthProvider.display_name == display_name,
            )
        )
        return result.scalar_one_or_none()

    async def create_provider(
        self,
        *,
        tenant_id: int,
        provider_type: str,
        display_name: str,
        enabled: bool,
        config: dict,
        identity_source_id: int,
    ) -> AuthProvider:
        encrypted = self._cipher.encrypt_dict(config, sensitive_fields=_CLIENT_SECRET_FIELDS)
        provider = AuthProvider(
            tenant_id=tenant_id,
            provider_type=provider_type,
            display_name=display_name,
            enabled=enabled,
            config_json=encrypted,
            identity_source_id=identity_source_id,
        )
        self.db.add(provider)
        await self.db.flush()
        await self.db.refresh(provider)
        return provider

    async def update_provider(self, provider: AuthProvider) -> AuthProvider:
        await self.db.flush()
        await self.db.refresh(provider)
        return provider

    async def delete_provider(self, provider: AuthProvider) -> None:
        await self.db.delete(provider)
        await self.db.flush()

    def decrypt_provider_config(self, provider: AuthProvider) -> dict:
        return self._cipher.decrypt_dict(provider.config_json or {})

    def encrypt_config(self, config: dict) -> dict:
        return self._cipher.encrypt_dict(config, sensitive_fields=_CLIENT_SECRET_FIELDS)

    # ---------- External identities (delegated to shared platform kernel) ----------

    async def get_identity_by_subject(
        self, tenant_id: int, identity_source_id: int, external_subject: str
    ):
        return await self._identity_repo.get_identity_by_subject(
            tenant_id, identity_source_id, external_subject
        )

    async def list_pending_identities(self, tenant_id: int):
        return await self._identity_repo.list_pending_identities(tenant_id)

    async def get_identity(self, tenant_id: int, identity_id: int):
        return await self._identity_repo.get_identity(tenant_id, identity_id)

    async def create_identity(self, **kwargs):
        return await self._identity_repo.create_identity(**kwargs)

    async def update_identity_status(self, tenant_id: int, identity_id: int, status: str, user_id: int | None = None):
        return await self._identity_repo.update_identity_status(tenant_id, identity_id, status, user_id=user_id)

    async def count_members_by_email(self, tenant_id: int, email: str):
        return await self._identity_repo.count_members_by_email(tenant_id, email)

    # ---------- Login states (PKCE) ----------

    async def create_login_state(
        self,
        *,
        tenant_id: int,
        provider_id: int,
        state: str,
        code_verifier: str,
        nonce: str,
        ttl_seconds: int = 600,
    ) -> SsoLoginState:
        row = SsoLoginState(
            tenant_id=tenant_id,
            provider_id=provider_id,
            state=state,
            code_verifier=code_verifier,
            nonce=nonce,
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def consume_login_state(self, state: str) -> SsoLoginState | None:
        """Atomically load and mark consumed a non-expired, non-consumed state."""
        result = await self.db.execute(
            select(SsoLoginState).where(
                SsoLoginState.state == state,
                SsoLoginState.consumed.is_(False),
                SsoLoginState.expires_at > datetime.now(UTC),
            )
        )
        row = result.scalar_one_or_none()
        if not row:
            return None
        row.consumed = True
        await self.db.flush()
        return row

    # ---------- Login tickets ----------

    async def create_login_ticket(self, *, tenant_id: int, user_id: int, ttl_seconds: int = 120) -> SsoLoginTicket:
        import secrets

        row = SsoLoginTicket(
            tenant_id=tenant_id,
            user_id=user_id,
            ticket=secrets.token_urlsafe(32),
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
        )
        self.db.add(row)
        await self.db.flush()
        await self.db.refresh(row)
        return row

    async def consume_login_ticket(self, ticket: str) -> SsoLoginTicket | None:
        result = await self.db.execute(
            select(SsoLoginTicket).where(
                SsoLoginTicket.ticket == ticket,
                SsoLoginTicket.consumed.is_(False),
                SsoLoginTicket.expires_at > datetime.now(UTC),
            )
        )
        row = result.scalar_one_or_none()
        if not row:
            return None
        row.consumed = True
        await self.db.flush()
        return row

    # ---------- Tenant SSO settings ----------

    async def get_tenant(self, tenant_id: int) -> Tenant | None:
        result = await self.db.execute(select(Tenant).where(Tenant.id == tenant_id))
        return result.scalar_one_or_none()

