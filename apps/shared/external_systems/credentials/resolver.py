"""Resolve effective credentials for shared vs user credential modes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from apps.shared.core.exceptions import IntegrationNotConnectedError
from apps.shared.db.models import DataSource, UserIntegrationCredential
from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import RESOURCE_TYPE_API_CONNECTOR, RESOURCE_TYPE_DATA_SOURCE
from apps.shared.external_systems.credentials.domain import AUTH_TYPE_OAUTH2, CREDENTIAL_STATUS_ACTIVE
from apps.shared.external_systems.credentials.repository import UserIntegrationCredentialRepository
from apps.shared.external_systems.credentials.user_secrets_policy import (
    USER_BINDING_POLICY,
    prepare_user_binding_secrets_for_storage,
)
from apps.shared.external_systems.data_source.config_secrets_policy import (
    DATA_SOURCE_CONFIG_POLICY,
    decrypt_data_source_config_from_storage,
)
from apps.shared.external_systems.domain.types import CREDENTIAL_MODE_USER, IntegrationPurpose
from apps.shared.utils.field_cipher import FieldCipher
from apps.shared.utils.secret_engines import strip_template

__all__ = ["IntegrationCredentialResolver"]


class IntegrationCredentialResolver:
    def __init__(self, db_session, cipher: FieldCipher | None = None):
        self.db_session = db_session
        self.cipher = cipher or FieldCipher()
        self.repo = UserIntegrationCredentialRepository(db_session)

    async def resolve_data_source_config(
        self,
        *,
        data_source: DataSource,
        actor: ActorContext | None,
        purpose: IntegrationPurpose,
    ) -> dict[str, Any]:
        base = decrypt_data_source_config_from_storage(
            data_source.config or {},
            cipher=self.cipher,
        )
        mode = getattr(data_source, "credential_mode", None) or "shared"
        if data_source.managed or mode != CREDENTIAL_MODE_USER:
            return base

        if actor is None:
            raise IntegrationNotConnectedError(
                "Actor required for user-mode data source",
                {"code": "INTEGRATION_NOT_CONNECTED", "resource_type": RESOURCE_TYPE_DATA_SOURCE},
            )

        binding, user_secrets = await self._load_active_user_secrets(
            tenant_id=data_source.tenant_id,
            user_id=actor.user_id,
            resource_type=RESOURCE_TYPE_DATA_SOURCE,
            resource_id=data_source.id,
        )
        if binding.auth_type == AUTH_TYPE_OAUTH2:
            from apps.shared.external_systems.data_source.user_oauth import oauth_token_refresh_template

            template = oauth_token_refresh_template(data_source.config or {}, cipher=self.cipher)
            user_secrets = await self._maybe_refresh_oauth2_user_secrets(
                binding=binding,
                template=template,
                user_secrets=user_secrets,
                resource_type=RESOURCE_TYPE_DATA_SOURCE,
            )
            overlay = {"password": user_secrets.get("access_token")}
        else:
            overlay = user_secrets
        template_strip = DATA_SOURCE_CONFIG_POLICY.template_strip
        base_stripped = strip_template(base, template_strip) if template_strip else base
        merged = {**base_stripped, **overlay}
        return merged

    async def resolve_api_connector_auth_config(
        self,
        *,
        connector,
        actor: ActorContext | None,
        purpose: IntegrationPurpose,
    ) -> dict[str, Any]:
        from apps.shared.external_systems.api_connector.auth_config_secrets_policy import (
            decrypt_auth_config_from_storage,
        )
        from apps.shared.external_systems.api_connector.domain import ApiConnectorCredentialSubject

        subject = connector if isinstance(connector, ApiConnectorCredentialSubject) else None
        if subject is None:
            raise TypeError("connector must be ApiConnectorCredentialSubject")

        template = decrypt_auth_config_from_storage(subject.auth_config_encrypted, cipher=self.cipher)
        mode = subject.credential_mode or "shared"
        if mode != CREDENTIAL_MODE_USER:
            return template

        if actor is None:
            raise IntegrationNotConnectedError(
                "Actor required for user-mode API connector",
                {"code": "INTEGRATION_NOT_CONNECTED", "resource_type": RESOURCE_TYPE_API_CONNECTOR},
            )

        binding, user_secrets = await self._load_active_user_secrets(
            tenant_id=subject.tenant_id,
            user_id=actor.user_id,
            resource_type=RESOURCE_TYPE_API_CONNECTOR,
            resource_id=subject.id,
        )
        if subject.auth_type == AUTH_TYPE_OAUTH2:
            user_secrets = await self._maybe_refresh_oauth2_user_secrets(
                binding=binding,
                template=template,
                user_secrets=user_secrets,
                resource_type=RESOURCE_TYPE_API_CONNECTOR,
            )
        return self._merge_user_secrets_into_connector_template(
            template=template,
            user_secrets=user_secrets,
            auth_type=subject.auth_type,
        )


    async def _load_active_user_secrets(
        self,
        *,
        tenant_id: int,
        user_id: int,
        resource_type: str,
        resource_id: int,
    ) -> tuple[UserIntegrationCredential, dict[str, Any]]:
        """Load an active binding and decrypt secrets without failing on near-expiry.

        OAuth connectors may refresh when expiry is imminent; callers decide refresh vs error.
        """
        binding = await self.repo.get_binding(
            tenant_id=tenant_id,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        if binding is None or binding.status != CREDENTIAL_STATUS_ACTIVE:
            raise IntegrationNotConnectedError(
                "Connect your account to use this integration",
                {
                    "code": "INTEGRATION_NOT_CONNECTED",
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                },
            )
        user_secrets = self.cipher.decrypt_dict(
            binding.secrets_enc, sensitive_fields=USER_BINDING_POLICY.encrypt_leaves
        )
        return binding, user_secrets


    async def _maybe_refresh_oauth2_user_secrets(
        self,
        *,
        binding: UserIntegrationCredential,
        template: dict[str, Any],
        user_secrets: dict[str, Any],
        resource_type: str,
    ) -> dict[str, Any]:
        from apps.shared.external_systems.oauth.refresh import maybe_refresh_oauth2_secrets

        tokens = await maybe_refresh_oauth2_secrets(
            auth_type=AUTH_TYPE_OAUTH2,
            oauth_template=template,
            user_secrets=user_secrets,
            expires_at=binding.expires_at,
            resource_type=resource_type,
        )
        if tokens is None:
            return user_secrets
        refreshed = {**user_secrets, **tokens.to_secrets()}
        binding.secrets_enc = prepare_user_binding_secrets_for_storage(refreshed, cipher=self.cipher)
        binding.expires_at = tokens.expires_at
        binding.updated_at = datetime.now(UTC)
        await self.db_session.flush()
        return refreshed

    @staticmethod
    def _merge_user_secrets_into_connector_template(
        *,
        template: dict[str, Any],
        user_secrets: dict[str, Any],
        auth_type: str,
    ) -> dict[str, Any]:
        from apps.shared.external_systems.byot_template_strip import strip_connector_auth_user_mode_template

        stripped = strip_connector_auth_user_mode_template(template, auth_type=auth_type)
        return {**stripped, **user_secrets}

    def _binding_shows_expired_status(self, row: UserIntegrationCredential) -> bool:
        """UI 'expired' means reconnect is required, not merely stale access-token TTL."""
        if row.expires_at is None:
            return False
        if row.expires_at.replace(tzinfo=UTC) >= datetime.now(UTC):
            return False
        if row.auth_type == AUTH_TYPE_OAUTH2:
            user_secrets = self.cipher.decrypt_dict(
                row.secrets_enc, sensitive_fields=USER_BINDING_POLICY.encrypt_leaves
            )
            refresh_token = user_secrets.get("refresh_token")
            if isinstance(refresh_token, str) and refresh_token.strip():
                return False
        return True

    async def connection_status_for_actor(
        self,
        *,
        tenant_id: int,
        user_id: int,
        resource_type: str,
        resource_id: int,
    ) -> tuple[str, UserIntegrationCredential | None]:
        from apps.shared.external_systems.domain.types import (
            USER_CONNECTION_CONNECTED,
            USER_CONNECTION_EXPIRED,
            USER_CONNECTION_NOT_CONNECTED,
        )

        row = await self.repo.get_binding(
            tenant_id=tenant_id,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        if row is None or row.status != CREDENTIAL_STATUS_ACTIVE:
            return USER_CONNECTION_NOT_CONNECTED, row
        if self._binding_shows_expired_status(row):
            return USER_CONNECTION_EXPIRED, row
        return USER_CONNECTION_CONNECTED, row
