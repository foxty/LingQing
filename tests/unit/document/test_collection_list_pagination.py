"""Paginated document collection list + search."""

from __future__ import annotations

import pytest

from apps.shared.document.collection_service import DocumentCollectionService
from apps.shared.domain.actor import ActorContext
from tests.helpers.document_fixtures import create_document_collection, create_tenant_user


@pytest.mark.asyncio
async def test_list_collections_paginated_and_query_filter(async_db_session):
    tenant, admin = await create_tenant_user(
        async_db_session,
        tenant_name="pag_coll_tenant",
        username="pag_coll_admin",
        role="admin",
    )
    await create_document_collection(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=admin.id,
        name="Alpha Sales",
    )
    await create_document_collection(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=admin.id,
        name="Beta Marketing",
    )
    await create_document_collection(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=admin.id,
        name="Alpha Support",
    )

    service = DocumentCollectionService(tenant_id=tenant.id, db_session=async_db_session)
    actor = ActorContext(tenant_id=tenant.id, user_id=admin.id, user_role=admin.role)

    alpha_items, alpha_page = await service.list_collections_paginated_for_actor(
        actor=actor,
        page=1,
        page_size=10,
        query="Alpha",
    )
    assert alpha_page.total == 2
    assert {item.name for item in alpha_items} == {"Alpha Sales", "Alpha Support"}

    page_one, pagination = await service.list_collections_paginated_for_actor(
        actor=actor,
        page=1,
        page_size=1,
    )
    assert pagination.total == 3
    assert len(page_one) == 1
