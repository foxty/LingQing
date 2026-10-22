"""Paginated connector list preserves ACL + ABAC read semantics."""

from __future__ import annotations

import pytest

from apps.shared.api_connector.domain import RatePolicyDomain
from apps.shared.api_connector.service import ApiConnectorService
from apps.shared.db.models import AclGrant, ResourceAcl, Tenant, User
from apps.shared.domain.actor import ActorContext


@pytest.mark.asyncio
async def test_paginated_list_honors_acl_allow_grant(async_db_session):
    tenant = Tenant(name="pag_conn_acl_tenant", slug="pag_conn_acl_tenant", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    admin = User(username="pag_acl_admin", email=None, hashed_password="hashed", role="admin", tenant_id=tenant.id)
    viewer = User(username="pag_acl_viewer", email=None, hashed_password="hashed", role="viewer", tenant_id=tenant.id)
    async_db_session.add_all([admin, viewer])
    await async_db_session.flush()

    service = ApiConnectorService(tenant_id=tenant.id, db_session=async_db_session)
    connector = await service.create_connector(
        owner_id=admin.id,
        name="paginated-acl-connector",
        description=None,
        base_url="https://api.paginated.local",
        auth_type="none",
        auth_config={},
        rate_policy=RatePolicyDomain.from_raw({}),
        schema_source_type="openapi_upload",
        schema_source_url=None,
    )

    async_db_session.add(
        ResourceAcl(
            tenant_id=tenant.id,
            resource_type="api_connector",
            resource_id=connector.id,
            owner_id=connector.owner_id,
            status="active",
        )
    )
    async_db_session.add(
        AclGrant(
            tenant_id=tenant.id,
            resource_type="api_connector",
            resource_id=connector.id,
            principal_type="user",
            principal_id=str(viewer.id),
            permission="read",
            effect="allow",
            created_by=admin.id,
        )
    )
    await async_db_session.flush()

    actor = ActorContext(tenant_id=tenant.id, user_id=viewer.id, user_role=viewer.role)
    page_one, pagination = await service.list_connectors_paginated_for_actor(
        actor=actor,
        page=1,
        page_size=1,
    )
    assert pagination.total >= 1
    assert any(item.id == connector.id for item in page_one)

    filtered, filtered_page = await service.list_connectors_paginated_for_actor(
        actor=actor,
        page=1,
        page_size=20,
        query="paginated-acl",
    )
    assert filtered_page.total == 1
    assert filtered[0].id == connector.id
