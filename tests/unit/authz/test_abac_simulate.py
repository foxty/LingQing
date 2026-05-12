"""Unit tests for ABAC expression simulation on document collections."""

import pytest

from apps.shared.authz.authz_query_builder import evaluate_single_expression
from apps.shared.authz.dsl import DslParseError
from tests.helpers.document_fixtures import create_document, create_document_collection, create_tenant_user


@pytest.mark.asyncio
async def test_simulate_allows_when_expression_matches(async_db_session):
    tenant, user = await create_tenant_user(async_db_session, tenant_name="tenant_sim_allow", username="sim_u1")
    collection = await create_document_collection(async_db_session, tenant_id=tenant.id, owner_id=user.id)

    from apps.shared.db.models import TagBinding, TagKey, TagValue

    tag_key = TagKey(id=1, tenant_id=tenant.id, name="dept", description=None)
    async_db_session.add(tag_key)
    await async_db_session.commit()
    await async_db_session.refresh(tag_key)

    tag_value_sales = TagValue(id=1, tenant_id=tenant.id, key_id=tag_key.id, value="sales")
    async_db_session.add(tag_value_sales)
    await async_db_session.commit()
    await async_db_session.refresh(tag_value_sales)

    doc = await create_document(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=user.id,
        collection_id=collection.id,
        filename="sim-allowed.pdf",
        file_url="file://sim-allowed",
    )

    async_db_session.add_all(
        [
            TagBinding(
                id=1,
                tenant_id=tenant.id,
                resource_type="user",
                resource_id=user.id,
                tag_value_id=tag_value_sales.id,
            ),
            TagBinding(
                id=2,
                tenant_id=tenant.id,
                resource_type="document_collection",
                resource_id=collection.id,
                tag_value_id=tag_value_sales.id,
            ),
        ]
    )
    await async_db_session.commit()

    allowed, reason = await evaluate_single_expression(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        user_role=user.role,
        resource_type="document_collection",
        resource_id=collection.id,
        expression=':user.tags has "dept:sales" and :resource.tags has "dept:sales"',
    )

    assert allowed is True
    assert "AND" in reason


@pytest.mark.asyncio
async def test_simulate_denies_when_no_match(async_db_session):
    tenant, user = await create_tenant_user(async_db_session, tenant_name="tenant_sim_deny", username="sim_u2")
    collection = await create_document_collection(async_db_session, tenant_id=tenant.id, owner_id=user.id)
    await create_document(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=user.id,
        collection_id=collection.id,
        filename="sim-denied.pdf",
        file_url="file://sim-denied",
    )

    allowed, _reason = await evaluate_single_expression(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        user_role=user.role,
        resource_type="document_collection",
        resource_id=collection.id,
        expression=':user.tags has "dept:sales" and :resource.tags has "dept:sales"',
    )

    assert allowed is False


@pytest.mark.asyncio
async def test_simulate_user_role_equals(async_db_session):
    tenant, user = await create_tenant_user(
        async_db_session,
        tenant_name="tenant_sim_role",
        username="sim_admin",
        role="admin",
    )
    collection = await create_document_collection(async_db_session, tenant_id=tenant.id, owner_id=user.id)
    await create_document(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=user.id,
        collection_id=collection.id,
        filename="sim-role.pdf",
        file_url="file://sim-role",
    )

    allowed, reason = await evaluate_single_expression(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        user_role="admin",
        resource_type="document_collection",
        resource_id=collection.id,
        expression=':user.role equals "admin"',
    )

    assert allowed is True
    assert reason == "user.role equals 'admin'"


@pytest.mark.asyncio
async def test_simulate_invalid_expression_raises(async_db_session):
    tenant, user = await create_tenant_user(async_db_session, tenant_name="tenant_sim_invalid", username="sim_u3")
    collection = await create_document_collection(async_db_session, tenant_id=tenant.id, owner_id=user.id)
    await create_document(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=user.id,
        collection_id=collection.id,
        filename="sim-invalid.pdf",
        file_url="file://sim-invalid",
    )

    with pytest.raises(DslParseError):
        await evaluate_single_expression(
            db_session=async_db_session,
            tenant_id=tenant.id,
            user_id=user.id,
            user_role=user.role,
            resource_type="document_collection",
            resource_id=collection.id,
            expression="invalid expression",
        )
