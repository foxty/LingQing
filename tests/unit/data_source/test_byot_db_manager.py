"""BYOT: get_db_manager vs get_db_manager_for_actor behavior."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.shared.core.exceptions import ValidationError
from apps.shared.external_systems.data_source.service import DataSourceService
from apps.shared.db.models import DataSource
from apps.shared.domain.actor import ActorContext


def _service(repo) -> DataSourceService:
    return DataSourceService(
        tenant_id=10,
        data_source_repo=repo,
        asset_repo=SimpleNamespace(db=MagicMock()),
    )


@pytest.mark.asyncio
async def test_get_db_manager_rejects_user_mode_external_source():
    entity = DataSource(
        id=1,
        tenant_id=10,
        name="uc",
        type="databricks",
        managed=False,
        config={"host": "x"},
        credential_mode="user",
    )
    repo = SimpleNamespace(get_by_id_and_tenant=AsyncMock(return_value=entity), db=MagicMock())
    service = _service(repo)

    with pytest.raises(ValidationError, match="get_db_manager_for_actor"):
        await service.get_db_manager(1)


@pytest.mark.asyncio
async def test_get_db_manager_for_actor_resolves_via_resolver(monkeypatch):
    entity = DataSource(
        id=2,
        tenant_id=10,
        name="uc",
        type="databricks",
        managed=False,
        config={"host": "x"},
        credential_mode="user",
    )
    repo = SimpleNamespace(get_by_id_and_tenant=AsyncMock(return_value=entity), db=MagicMock())
    service = _service(repo)
    actor = ActorContext(tenant_id=10, user_id=5, user_role="viewer")

    fake_ctx = MagicMock()

    class _FakeResolver:
        def __init__(self, _db):
            pass

        async def resolve_data_source_config(self, **kwargs):
            return {"host": "x", "password": "user-pat"}

    monkeypatch.setattr(
        "apps.shared.external_systems.data_source.service.IntegrationCredentialResolver",
        _FakeResolver,
    )
    monkeypatch.setattr(
        "apps.shared.external_systems.data_source.service.get_db_manager_for_datasource",
        lambda domain: fake_ctx,
    )

    from datetime import UTC, datetime

    from apps.shared.external_systems.data_source.domain import DataSourceDomain
    from apps.shared.domain.value_objects import DatabaseConnectionVO

    def _fake_domain_with_connection(entity, connection):
        return DataSourceDomain(
            id=entity.id,
            tenant_id=entity.tenant_id,
            name=entity.name,
            type=entity.type,
            managed=entity.managed,
            connection=DatabaseConnectionVO.from_dict(
                {"type": "postgres", "host": "x", "database": "db", "username": "u", "password": "t"}
            ),
            description=None,
            owner_id=1,
            asset_count=0,
            credential_mode="user",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    monkeypatch.setattr(
        "apps.shared.external_systems.data_source.service.db_data_source_to_domain_with_connection",
        _fake_domain_with_connection,
    )

    manager = await service.get_db_manager_for_actor(2, actor)
    assert manager is fake_ctx
