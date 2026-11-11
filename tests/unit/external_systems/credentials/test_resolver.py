"""Unit tests for IntegrationCredentialResolver."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.shared.core.exceptions import IntegrationNotConnectedError
from apps.shared.db.models import DataSource, UserIntegrationCredential
from apps.shared.domain.actor import ActorContext
from apps.shared.external_systems.credentials.domain import (
    CREDENTIAL_MODE_USER,
    CREDENTIAL_STATUS_ACTIVE,
    IntegrationPurpose,
    RESOURCE_TYPE_DATA_SOURCE,
)
from apps.shared.external_systems.credentials.resolver import IntegrationCredentialResolver


@pytest.mark.asyncio
async def test_resolve_shared_mode_ignores_user_binding():
    db = MagicMock()
    entity = DataSource(
        id=1,
        tenant_id=10,
        name="ds",
        type="databricks",
        managed=False,
        config={"host": "x", "password": "shared-pat"},
        credential_mode="shared",
    )
    resolver = IntegrationCredentialResolver(db)
    resolver.repo.get_binding = AsyncMock(return_value=None)

    config = await resolver.resolve_data_source_config(
        data_source=entity,
        actor=None,
        purpose=IntegrationPurpose.QUERY,
    )
    assert config["password"] == "shared-pat"


@pytest.mark.asyncio
async def test_resolve_user_mode_requires_binding():
    db = MagicMock()
    entity = DataSource(
        id=2,
        tenant_id=10,
        name="ds",
        type="databricks",
        managed=False,
        config={"host": "x"},
        credential_mode=CREDENTIAL_MODE_USER,
    )
    actor = ActorContext(tenant_id=10, user_id=5, user_role="viewer")
    resolver = IntegrationCredentialResolver(db)
    resolver.repo.get_binding = AsyncMock(return_value=None)

    with pytest.raises(IntegrationNotConnectedError):
        await resolver.resolve_data_source_config(
            data_source=entity,
            actor=actor,
            purpose=IntegrationPurpose.QUERY,
        )


@pytest.mark.asyncio
async def test_resolve_user_mode_merges_secrets(monkeypatch):
    db = MagicMock()
    entity = DataSource(
        id=3,
        tenant_id=10,
        name="ds",
        type="databricks",
        managed=False,
        config={"host": "x", "password": "admin-should-strip"},
        credential_mode=CREDENTIAL_MODE_USER,
    )
    actor = ActorContext(tenant_id=10, user_id=7, user_role="member")
    binding = UserIntegrationCredential(
        tenant_id=10,
        user_id=7,
        resource_type=RESOURCE_TYPE_DATA_SOURCE,
        resource_id=3,
        auth_type="pat",
        secrets_enc={"password": "enc"},
        status=CREDENTIAL_STATUS_ACTIVE,
    )
    resolver = IntegrationCredentialResolver(db)
    resolver.repo.get_binding = AsyncMock(return_value=binding)
    resolver.cipher.decrypt_dict = MagicMock(return_value={"password": "user-pat"})

    config = await resolver.resolve_data_source_config(
        data_source=entity,
        actor=actor,
        purpose=IntegrationPurpose.QUERY,
    )
    assert config["host"] == "x"
    assert config["password"] == "user-pat"
    assert "admin-should-strip" not in config.values()
