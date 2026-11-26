"""Resolve effective credentials for shared vs user credential modes."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from apps.shared.core.exceptions import IntegrationNotConnectedError
from apps.shared.db.models import ApiConnector, DataSource, UserIntegrationCredential
from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import RESOURCE_TYPE_API_CONNECTOR, RESOURCE_TYPE_DATA_SOURCE
from apps.shared.external_systems.credentials.domain import AUTH_TYPE_OAUTH2, CREDENTIAL_STATUS_ACTIVE
from apps.shared.external_systems.credentials.repository import UserIntegrationCredentialRepository
from apps.shared.external_systems.credentials.sensitive_config import (
    API_CONNECTOR_USER_MODE_STRIP_KEYS,
    DATA_SOURCE_USER_MODE_STRIP_KEYS,
    OAUTH2_USER_TOKEN_KEYS,
    USER_INTEGRATION_SENSITIVE_LEAF_KEYS,
)
from apps.shared.external_systems.domain.types import CREDENTIAL_MODE_USER, IntegrationPurpose
from apps.shared.utils.field_cipher import FieldCipher, strip_sensitive_fields

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
        base = deepcopy(data_source.config or {})
        mode = getattr(data_source, "credential_mode", None) or "shared"
        if data_source.managed or mode != CREDENTIAL_MODE_USER:
            return base

        if actor is None:
            raise IntegrationNotConnectedError(
                "Actor required for user-mode data source",
                {"code": "INTEGRATION_NOT_CONNECTED", "resource_type": RESOURCE_TYPE_DATA_SOURCE},
            )

        binding = await self._require_active_binding(
            tenant_id=data_source.tenant_id,
            user_id=actor.user_id,
            resource_type=RESOURCE_TYPE_DATA_SOURCE,
            resource_id=data_source.id,
        )
        user_secrets = self.cipher.decrypt_dict(
            binding.secrets_enc, sensitive_fields=USER_INTEGRATION_SENSITIVE_LEAF_KEYS
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
        merged = {**strip_sensitive_fields(base, sensitive_keys=DATA_SOURCE_USER_MODE_STRIP_KEYS), **overlay}
        return merged

    async def resolve_api_connector_auth_config(
        self,
        *,
        connector: ApiConnector,
        actor: ActorContext | None,
        purpose: IntegrationPurpose,
    ) -> dict[str, Any]:
        template = self._decrypt_connector_auth_template(connector)
        mode = getattr(connector, "credential_mode", None) or "shared"
        if mode != CREDENTIAL_MODE_USER:
            return template

        if actor is None:
            raise IntegrationNotConnectedError(
                "Actor required for user-mode API connector",
                {"code": "INTEGRATION_NOT_CONNECTED", "resource_type": RESOURCE_TYPE_API_CONNECTOR},
            )

        binding, user_secrets = await self._load_active_user_secrets(
            tenant_id=connector.tenant_id,
            user_id=actor.user_id,
            resource_type=RESOURCE_TYPE_API_CONNECTOR,
            resource_id=connector.id,
        )
        if connector.auth_type == AUTH_TYPE_OAUTH2:
            user_secrets = await self._maybe_refresh_oauth2_user_secrets(
                binding=binding,
                template=template,
                user_secrets=user_secrets,
                resource_type=RESOURCE_TYPE_API_CONNECTOR,
            )
        return self._merge_user_secrets_into_connector_template(
            template=template,
            user_secrets=user_secrets,
            auth_type=connector.auth_type,
        )

    def _decrypt_connector_auth_template(self, connector: ApiConnector) -> dict[str, Any]:
        raw_template = connector.auth_config or {}
        return self.cipher.decrypt_dict(raw_template, sensitive_fields=USER_INTEGRATION_SENSITIVE_LEAF_KEYS)

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
            binding.secrets_enc, sensitive_fields=USER_INTEGRATION_SENSITIVE_LEAF_KEYS
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
        binding.secrets_enc = self.cipher.encrypt_dict(refreshed, sensitive_fields=USER_INTEGRATION_SENSITIVE_LEAF_KEYS)
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
        strip_keys = OAUTH2_USER_TOKEN_KEYS if auth_type == "oauth2" else API_CONNECTOR_USER_MODE_STRIP_KEYS
        return {**strip_sensitive_fields(template, sensitive_keys=strip_keys), **user_secrets}

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
        if row.expires_at and row.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
            return USER_CONNECTION_EXPIRED, row
        return USER_CONNECTION_CONNECTED, row

    async def _require_active_binding(
        self,
        *,
        tenant_id: int,
        user_id: int,
        resource_type: str,
        resource_id: int,
    ):
        row = await self.repo.get_binding(
            tenant_id=tenant_id,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        if row is None or row.status != CREDENTIAL_STATUS_ACTIVE:
            raise IntegrationNotConnectedError(
                "Connect your account to use this integration",
                {
                    "code": "INTEGRATION_NOT_CONNECTED",
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                },
            )
        if row.expires_at and row.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
            raise IntegrationNotConnectedError(
                "Integration credentials expired; reconnect to continue",
                {"code": "INTEGRATION_CREDENTIAL_EXPIRED", "resource_type": resource_type},
            )
        return row
