"""Unit tests for tenant provisioning service."""

import pytest
from sqlalchemy import select

from apps.tenant_app_service.tenant.provisioning_service import TenantProvisioningService
from apps.shared.db.models import Tenant


class _DummyProvisioningExecutor:
    async def provision_database(self, **kwargs):
        return None

    async def drop_database(self, db_name: str):
        return None

    async def drop_role(self, role_name: str):
        return None


@pytest.mark.asyncio
async def test_provision_tenant_calls_default_seeders(async_db_session, monkeypatch):
    calls: list[tuple[str, int]] = []

    async def _fake_seed_default_tags(db, tenant_id: int):
        calls.append(("tags", tenant_id))

    async def _fake_seed_default_policies(db, tenant_id: int):
        calls.append(("policies", tenant_id))

    async def _fake_reconcile_for_tenant(tenant_id: int) -> int:
        calls.append(("system_tasks", tenant_id))
        return 6

    monkeypatch.setattr(
        "apps.tenant_app_service.tenant.provisioning_service.seed_default_tags",
        _fake_seed_default_tags,
    )
    monkeypatch.setattr(
        "apps.tenant_app_service.tenant.provisioning_service.seed_default_policies",
        _fake_seed_default_policies,
    )
    monkeypatch.setattr(
        "apps.tenant_app_service.tenant.provisioning_service.reconcile_for_tenant",
        _fake_reconcile_for_tenant,
    )

    service = TenantProvisioningService(async_db_session, _DummyProvisioningExecutor())

    result = await service.provision_tenant(
        name="Provisioning Test Tenant",
        slug="provisioning_test_tenant",
        description="test",
    )

    tenant_id = result["id"]
    assert result["name"] == "Provisioning Test Tenant"
    assert result["slug"] == "provisioning_test_tenant"
    assert ("tags", tenant_id) in calls
    assert ("policies", tenant_id) in calls
    assert ("system_tasks", tenant_id) in calls

    tenant_row = await async_db_session.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = tenant_row.scalar_one_or_none()
    assert tenant is not None
