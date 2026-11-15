"""Repository isolation for user_integration_credentials."""

import pytest

from apps.shared.db.models import DataSource, Tenant, User
from apps.shared.external_systems.credentials.domain import RESOURCE_TYPE_DATA_SOURCE
from apps.shared.external_systems.credentials.repository import UserIntegrationCredentialRepository
from apps.shared.utils.field_cipher import FieldCipher


@pytest.mark.asyncio
async def test_bindings_are_scoped_per_user_id(async_db_session):
    tenant = Tenant(name="byot-tenant", slug="byot-tenant", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user_a = User(
        username="user_a",
        email=None,
        hashed_password="h",
        role="member",
        tenant_id=tenant.id,
    )
    user_b = User(
        username="user_b",
        email=None,
        hashed_password="h",
        role="member",
        tenant_id=tenant.id,
    )
    async_db_session.add_all([user_a, user_b])
    await async_db_session.flush()

    ds = DataSource(
        tenant_id=tenant.id,
        owner_id=user_a.id,
        name="shared-ds",
        type="databricks",
        managed=False,
        config={"host": "https://x"},
        credential_mode="user",
    )
    async_db_session.add(ds)
    await async_db_session.flush()

    cipher = FieldCipher()
    repo = UserIntegrationCredentialRepository(async_db_session)
    secrets_enc = cipher.encrypt_dict({"password": "pat-a"}, sensitive_fields={"password"})

    await repo.upsert_binding(
        tenant_id=tenant.id,
        user_id=user_a.id,
        resource_type=RESOURCE_TYPE_DATA_SOURCE,
        resource_id=ds.id,
        auth_type="pat",
        secrets_enc=secrets_enc,
        account_label="A",
    )

    row_a = await repo.get_binding(
        tenant_id=tenant.id,
        user_id=user_a.id,
        resource_type=RESOURCE_TYPE_DATA_SOURCE,
        resource_id=ds.id,
    )
    row_b = await repo.get_binding(
        tenant_id=tenant.id,
        user_id=user_b.id,
        resource_type=RESOURCE_TYPE_DATA_SOURCE,
        resource_id=ds.id,
    )

    assert row_a is not None
    assert row_b is None
    assert row_a.user_id == user_a.id
