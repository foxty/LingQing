"""Resolve effective credentials for shared vs user credential modes."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from apps.shared.core.exceptions import IntegrationNotConnectedError
from apps.shared.db.models import ApiConnector, DataSource, UserIntegrationCredential
from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import RESOURCE_TYPE_API_CONNECTOR, RESOURCE_TYPE_DATA_SOURCE
from apps.shared.external_systems.credentials.domain import CREDENTIAL_STATUS_ACTIVE
from apps.shared.external_systems.credentials.repository import UserIntegrationCredentialRepository
from apps.shared.external_systems.domain.types import CREDENTIAL_MODE_USER, IntegrationPurpose
from apps.shared.utils.field_cipher import SENSITIVE_FIELD_KEYS, FieldCipher, strip_sensitive_fields

__all__ = ["IntegrationCredentialResolver", "strip_sensitive_fields"]


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
        user_secrets = self.cipher.decrypt_dict(binding.secrets_enc, sensitive_fields=SENSITIVE_FIELD_KEYS)
        merged = {**strip_sensitive_fields(base), **user_secrets}
        return merged

    async def resolve_api_connector_auth_config(
        self,
        *,
        connector: ApiConnector,
        actor: ActorContext | None,
        purpose: IntegrationPurpose,
    ) -> dict[str, Any]:
        from apps.shared.utils.field_cipher import AUTH_CONFIG_SENSITIVE_FIELDS

        mode = getattr(connector, "credential_mode", None) or "shared"
        if mode != CREDENTIAL_MODE_USER:
            raw = connector.auth_config or {}
            if self.cipher and raw:
                return self.cipher.decrypt_dict(raw, sensitive_fields=AUTH_CONFIG_SENSITIVE_FIELDS)
            return dict(raw)

        if actor is None:
            raise IntegrationNotConnectedError(
                "Actor required for user-mode API connector",
                {"code": "INTEGRATION_NOT_CONNECTED", "resource_type": RESOURCE_TYPE_API_CONNECTOR},
            )

        binding = await self._require_active_binding(
            tenant_id=connector.tenant_id,
            user_id=actor.user_id,
            resource_type=RESOURCE_TYPE_API_CONNECTOR,
            resource_id=connector.id,
        )
        template = strip_sensitive_fields(connector.auth_config or {})
        user_secrets = self.cipher.decrypt_dict(binding.secrets_enc, sensitive_fields=SENSITIVE_FIELD_KEYS)
        return {**template, **user_secrets}

    async def connection_status_for_actor(
        self,
        *,
        tenant_id: int,
        user_id: int,
        resource_type: str,
        resource_id: int,
    ) -> tuple[str, UserIntegrationCredential | None]:
        from apps.shared.external_systems.credentials.dtos import (
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
