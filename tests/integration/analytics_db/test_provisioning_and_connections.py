"""Managed analytics DB: provisioning, URL encoding, and connection tests."""

from __future__ import annotations

import pytest

from apps.shared.infra.analytics_db.manager_factory import create_db_manager_from_config
from tests.integration.analytics_db.conftest import SPECIAL_ROLE_PASSWORD


@pytest.mark.asyncio
async def test_provisioned_analytics_db_connects_with_url_encoded_password(provisioned_analytics_stack):
    conn = provisioned_analytics_stack["connection"]
    assert conn.password == SPECIAL_ROLE_PASSWORD
    assert "&" in conn.password

    async with create_db_manager_from_config(
        tenant_id=provisioned_analytics_stack["tenant_id"],
        db_type="postgres",
        config=conn.to_dict(),
        managed=True,
    ) as mgr:
        ok, message = await mgr.test_connection()
        assert ok, message


@pytest.mark.asyncio
async def test_managed_data_source_get_db_manager_test_connection(provisioned_analytics_stack):
    ds_service = provisioned_analytics_stack["ds_service"]
    data_source_id = provisioned_analytics_stack["data_source_id"]
    actor = provisioned_analytics_stack["actor"]

    db_manager = await ds_service.get_db_manager_for_actor(data_source_id, actor)
    async with db_manager as mgr:
        ok, message = await mgr.test_connection()
    assert ok, message


@pytest.mark.asyncio
async def test_unsaved_test_connection_accepts_provisioned_config(provisioned_analytics_stack):
    ds_service = provisioned_analytics_stack["ds_service"]
    result = await ds_service.test_connection("postgres", provisioned_analytics_stack["connection"].to_dict())
    assert result.success is True