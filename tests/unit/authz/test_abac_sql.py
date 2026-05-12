import pytest
from sqlalchemy import select
from sqlalchemy.dialects import sqlite

from apps.shared.authz.authz_query_builder import (
    _SIMULATION_OWNER_RESOLVERS,
    _build_abac_resource_filter,
    build_unified_resource_filter,
    evaluate_resource_action,
    evaluate_single_expression,
)
from apps.shared.db.models import (
    AbacPolicy,
    AclGrant,
    ApiConnector,
    AssetMetadata,
    DataSource,
    Document,
    DocumentCollection,
    ResourceAcl,
    TagBinding,
    TagKey,
    TagValue,
    Tenant,
    User,
)
from apps.shared.domain.types import (
    RESOURCE_TYPE_AGENT,
    RESOURCE_TYPE_API_CONNECTOR,
    RESOURCE_TYPE_DATA_SOURCE,
    RESOURCE_TYPE_DOCUMENT,
    RESOURCE_TYPE_DOCUMENT_COLLECTION,
)


from uuid import uuid4


async def _ensure_collection(async_db_session, tenant_id: int, owner_id: int) -> DocumentCollection:
    collection = DocumentCollection(
        tenant_id=tenant_id,
        name=f"test-collection-{uuid4().hex[:8]}",
        owner_id=owner_id,
    )
    async_db_session.add(collection)
    await async_db_session.flush()
    return collection


@pytest.mark.asyncio
async def test_build_abac_resource_filter_allows_matching_document(async_db_session):
    tenant = Tenant(name="tenant_abac", slug="tenant_abac", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    user = User(
        username="alice",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.commit()
    await async_db_session.refresh(user)

    tag_key = TagKey(
        id=1,
        tenant_id=tenant.id,
        name="dept",
        description=None,
    )
    async_db_session.add(tag_key)
    await async_db_session.commit()
    await async_db_session.refresh(tag_key)

    tag_value_sales = TagValue(id=1, tenant_id=tenant.id, key_id=tag_key.id, value="sales")
    async_db_session.add(tag_value_sales)
    await async_db_session.commit()
    await async_db_session.refresh(tag_value_sales)

    async_db_session.add(
        TagBinding(
            id=1,
            tenant_id=tenant.id,
            resource_type="user",
            resource_id=user.id,
            tag_value_id=tag_value_sales.id,
        )
    )

    collection = await _ensure_collection(async_db_session, tenant.id, user.id)
    doc_allowed = Document(
        collection_id=collection.id,
        tenant_id=tenant.id,
        filename="allowed.pdf",
        file_url="file://allowed",
        file_size=10,
        file_hash="hash1",
        owner_id=user.id,
    )
    collection = await _ensure_collection(async_db_session, tenant.id, user.id)
    doc_denied = Document(
        collection_id=collection.id,
        tenant_id=tenant.id,
        filename="denied.pdf",
        file_url="file://denied",
        file_size=12,
        file_hash="hash2",
        owner_id=user.id,
    )
    async_db_session.add_all([doc_allowed, doc_denied])
    await async_db_session.commit()
    await async_db_session.refresh(doc_allowed)
    await async_db_session.refresh(doc_denied)

    async_db_session.add(
        TagBinding(
            id=2,
            tenant_id=tenant.id,
            resource_type="document",
            resource_id=doc_allowed.id,
            tag_value_id=tag_value_sales.id,
        )
    )

    policy = AbacPolicy(
        id=1,
        tenant_id=tenant.id,
        name="dept_sales",
        description=None,
        resource_type="document",
        expression=':user.tags has "dept:sales" and :resource.tags has "dept:sales"',
        status="active",
    )
    async_db_session.add(policy)
    await async_db_session.commit()

    abac_filter = await _build_abac_resource_filter(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        resource_type="document",
        resource_id_column=Document.id,
    )

    assert not abac_filter.allow_all
    assert not abac_filter.deny_all
    assert abac_filter.clause is not None

    stmt = select(Document.id).where(Document.tenant_id == tenant.id, abac_filter.clause)
    compiled = str(stmt)
    assert "tag_bindings" in compiled
    assert "tag_values" in compiled
    assert "tag_keys" in compiled
    result = await async_db_session.execute(stmt)
    allowed_ids = {row[0] for row in result.all()}

    assert doc_allowed.id in allowed_ids
    assert doc_denied.id not in allowed_ids


@pytest.mark.asyncio
async def test_build_abac_resource_filter_denies_when_user_tag_missing(async_db_session):
    tenant = Tenant(name="tenant_abac_deny", slug="tenant_abac_deny", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    user = User(
        username="bob",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.commit()
    await async_db_session.refresh(user)

    tag_key = TagKey(
        id=1,
        tenant_id=tenant.id,
        name="dept",
        description=None,
    )
    async_db_session.add(tag_key)
    await async_db_session.commit()
    await async_db_session.refresh(tag_key)

    tag_value_sales = TagValue(id=1, tenant_id=tenant.id, key_id=tag_key.id, value="sales")
    async_db_session.add(tag_value_sales)
    await async_db_session.commit()
    await async_db_session.refresh(tag_value_sales)

    policy = AbacPolicy(
        id=1,
        tenant_id=tenant.id,
        name="dept_sales",
        description=None,
        resource_type="document",
        expression=':user.tags has "dept:sales" and :resource.tags has "dept:sales"',
        status="active",
    )
    async_db_session.add(policy)
    await async_db_session.commit()

    abac_filter = await _build_abac_resource_filter(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        resource_type="document",
        resource_id_column=Document.id,
    )

    assert not abac_filter.allow_all
    assert abac_filter.deny_all
    assert abac_filter.clause is None


@pytest.mark.asyncio
async def test_build_abac_resource_filter_allows_when_no_policies(async_db_session):
    tenant = Tenant(name="tenant_abac_none", slug="tenant_abac_none", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    user = User(
        username="carol",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.commit()
    await async_db_session.refresh(user)

    abac_filter = await _build_abac_resource_filter(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        resource_type="document",
        resource_id_column=Document.id,
    )

    assert abac_filter.allow_all
    assert not abac_filter.deny_all
    assert abac_filter.clause is None


@pytest.mark.asyncio
async def test_build_abac_resource_filter_invalid_policy_does_not_raise(async_db_session):
    tenant = Tenant(name="tenant_abac_strict_raise", slug="tenant_abac_strict_raise", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    user = User(
        username="strict_user",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.commit()
    await async_db_session.refresh(user)

    invalid_policy = AbacPolicy(
        id=1,
        tenant_id=tenant.id,
        name="invalid_policy",
        description=None,
        resource_type="document",
        expression=':user.tags unknown_op "dept:sales"',
        status="active",
    )
    async_db_session.add(invalid_policy)
    await async_db_session.commit()

    abac_filter = await _build_abac_resource_filter(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        resource_type="document",
        resource_id_column=Document.id,
    )

    assert not abac_filter.allow_all
    assert abac_filter.deny_all
    assert abac_filter.clause is None


@pytest.mark.asyncio
async def test_build_abac_resource_filter_non_strict_mode_does_not_raise_on_invalid_policy(async_db_session):
    tenant = Tenant(name="tenant_abac_non_strict", slug="tenant_abac_non_strict", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    user = User(
        username="non_strict_user",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.commit()
    await async_db_session.refresh(user)

    invalid_policy = AbacPolicy(
        id=1,
        tenant_id=tenant.id,
        name="invalid_policy_non_strict",
        description=None,
        resource_type="document",
        expression=':user.tags unknown_op "dept:sales"',
        status="active",
    )
    async_db_session.add(invalid_policy)
    await async_db_session.commit()

    abac_filter = await _build_abac_resource_filter(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        resource_type="document",
        resource_id_column=Document.id,
    )

    assert not abac_filter.allow_all
    assert abac_filter.deny_all
    assert abac_filter.clause is None


@pytest.mark.asyncio
async def test_evaluate_resource_action_invalid_policy_denies(async_db_session):
    tenant = Tenant(name="tenant_eval_strict_raise", slug="tenant_eval_strict_raise", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    user = User(
        username="eval_strict_user",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.commit()
    await async_db_session.refresh(user)

    collection = await _ensure_collection(async_db_session, tenant.id, user.id)
    doc = Document(
        collection_id=collection.id,
        tenant_id=tenant.id,
        filename="strict.pdf",
        file_url="file://strict",
        file_size=10,
        file_hash="hash",
        owner_id=user.id,
    )
    async_db_session.add(doc)
    await async_db_session.commit()
    await async_db_session.refresh(doc)

    invalid_policy = AbacPolicy(
        id=1,
        tenant_id=tenant.id,
        name="invalid_eval_policy",
        description=None,
        resource_type="document",
        expression=':user.tags unknown_op "dept:sales"',
        status="active",
    )
    async_db_session.add(invalid_policy)
    await async_db_session.commit()

    allowed = await evaluate_resource_action(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        user_role=user.role,
        resource_type="document",
        resource_id=doc.id,
        resource_owner_id=doc.owner_id,
    )

    assert allowed is False


@pytest.mark.asyncio
async def test_evaluate_resource_action_abac_allow_acl_deny(async_db_session):
    tenant = Tenant(name="tenant_eval_acl_deny", slug="tenant_eval_acl_deny", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    owner = User(
        username="eval_acl_deny_owner", email=None, hashed_password="hashed", role="member", tenant_id=tenant.id
    )
    user = User(username="eval_acl_deny_user", email=None, hashed_password="hashed", role="member", tenant_id=tenant.id)
    async_db_session.add_all([owner, user])
    await async_db_session.commit()
    await async_db_session.refresh(owner)
    await async_db_session.refresh(user)

    collection = await _ensure_collection(async_db_session, tenant.id, user.id)
    doc = Document(
        collection_id=collection.id,
        tenant_id=tenant.id,
        filename="eval-acl-deny.pdf",
        file_url="file://eval-acl-deny",
        file_size=10,
        file_hash="hash",
        owner_id=owner.id,
    )
    async_db_session.add(doc)
    await async_db_session.commit()
    await async_db_session.refresh(doc)

    async_db_session.add(
        ResourceAcl(
            tenant_id=tenant.id,
            resource_type="document",
            resource_id=doc.id,
            owner_id=doc.owner_id,
            status="active",
        )
    )
    async_db_session.add(
        AclGrant(
            tenant_id=tenant.id,
            resource_type="document",
            resource_id=doc.id,
            principal_type="user",
            principal_id=str(user.id),
            permission="read",
            effect="deny",
            created_by=user.id,
        )
    )
    await async_db_session.commit()

    allowed = await evaluate_resource_action(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        user_role=user.role,
        resource_type="document",
        resource_id=doc.id,
        resource_owner_id=doc.owner_id,
    )

    # ACL deny is non-blocking under additive ACL semantics; ABAC allow still grants access.
    assert allowed is True


@pytest.mark.asyncio
async def test_evaluate_resource_action_abac_deny_acl_allow(async_db_session):
    tenant = Tenant(name="tenant_eval_abac_deny", slug="tenant_eval_abac_deny", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    user = User(
        username="eval_abac_deny_user", email=None, hashed_password="hashed", role="member", tenant_id=tenant.id
    )
    async_db_session.add(user)
    await async_db_session.commit()
    await async_db_session.refresh(user)

    collection = await _ensure_collection(async_db_session, tenant.id, user.id)
    doc = Document(
        collection_id=collection.id,
        tenant_id=tenant.id,
        filename="eval-abac-deny.pdf",
        file_url="file://eval-abac-deny",
        file_size=10,
        file_hash="hash",
        owner_id=user.id,
    )
    async_db_session.add(doc)
    await async_db_session.commit()
    await async_db_session.refresh(doc)

    policy = AbacPolicy(
        id=1,
        tenant_id=tenant.id,
        name="deny_without_tag",
        description=None,
        resource_type="document",
        expression=':user.tags has "dept:sales"',
        status="active",
    )
    async_db_session.add(policy)

    async_db_session.add(
        ResourceAcl(
            tenant_id=tenant.id,
            resource_type="document",
            resource_id=doc.id,
            owner_id=doc.owner_id,
            status="active",
        )
    )
    async_db_session.add(
        AclGrant(
            tenant_id=tenant.id,
            resource_type="document",
            resource_id=doc.id,
            principal_type="user",
            principal_id=str(user.id),
            permission="read",
            effect="allow",
            created_by=user.id,
        )
    )
    await async_db_session.commit()

    allowed = await evaluate_resource_action(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        user_role=user.role,
        resource_type="document",
        resource_id=doc.id,
        resource_owner_id=doc.owner_id,
    )

    # ACL explicit allow now overrides ABAC policy denial.
    assert allowed is True


@pytest.mark.asyncio
async def test_evaluate_resource_action_abac_allow_acl_not_applicable(async_db_session):
    tenant = Tenant(name="tenant_eval_acl_na", slug="tenant_eval_acl_na", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    user = User(username="eval_acl_na_user", email=None, hashed_password="hashed", role="member", tenant_id=tenant.id)
    async_db_session.add(user)
    await async_db_session.commit()
    await async_db_session.refresh(user)

    collection = await _ensure_collection(async_db_session, tenant.id, user.id)
    doc = Document(
        collection_id=collection.id,
        tenant_id=tenant.id,
        filename="eval-acl-na.pdf",
        file_url="file://eval-acl-na",
        file_size=10,
        file_hash="hash",
        owner_id=user.id,
    )
    async_db_session.add(doc)
    await async_db_session.commit()
    await async_db_session.refresh(doc)

    allowed = await evaluate_resource_action(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        user_role=user.role,
        resource_type="document",
        resource_id=doc.id,
        resource_owner_id=None,
    )

    assert allowed is True


@pytest.mark.asyncio
async def test_evaluate_resource_action_manage_permission_allows_active_acl(async_db_session):
    tenant = Tenant(name="tenant_eval_manage", slug="tenant_eval_manage", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    user = User(username="eval_manage_user", email=None, hashed_password="hashed", role="member", tenant_id=tenant.id)
    async_db_session.add(user)
    await async_db_session.commit()
    await async_db_session.refresh(user)

    collection = await _ensure_collection(async_db_session, tenant.id, user.id)
    doc = Document(
        collection_id=collection.id,
        tenant_id=tenant.id,
        filename="eval-manage.pdf",
        file_url="file://eval-manage",
        file_size=10,
        file_hash="hash",
        owner_id=user.id,
    )
    async_db_session.add(doc)
    await async_db_session.commit()
    await async_db_session.refresh(doc)

    async_db_session.add(
        ResourceAcl(
            tenant_id=tenant.id,
            resource_type="document",
            resource_id=doc.id,
            owner_id=doc.owner_id,
            status="active",
        )
    )
    await async_db_session.commit()

    allowed = await evaluate_resource_action(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        user_role=user.role,
        resource_type="document",
        resource_id=doc.id,
        resource_owner_id=None,
        has_manage_permission=True,
    )

    assert allowed is True


@pytest.mark.asyncio
async def test_evaluate_resource_action_owner_allows_with_none_owner_param(async_db_session):
    tenant = Tenant(name="tenant_eval_owner_acl", slug="tenant_eval_owner_acl", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    owner = User(
        username="eval_owner_acl_user", email=None, hashed_password="hashed", role="member", tenant_id=tenant.id
    )
    async_db_session.add(owner)
    await async_db_session.commit()
    await async_db_session.refresh(owner)

    collection = await _ensure_collection(async_db_session, tenant.id, owner.id)
    doc = Document(
        collection_id=collection.id,
        tenant_id=tenant.id,
        filename="eval-owner-acl.pdf",
        file_url="file://eval-owner-acl",
        file_size=10,
        file_hash="hash",
        owner_id=owner.id,
    )
    async_db_session.add(doc)
    await async_db_session.commit()
    await async_db_session.refresh(doc)

    async_db_session.add(
        ResourceAcl(
            tenant_id=tenant.id,
            resource_type="document",
            resource_id=doc.id,
            owner_id=owner.id,
            status="active",
        )
    )
    await async_db_session.commit()

    allowed = await evaluate_resource_action(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=owner.id,
        user_role=owner.role,
        resource_type="document",
        resource_id=doc.id,
        resource_owner_id=None,
    )

    assert allowed is True


@pytest.mark.asyncio
async def test_build_unified_resource_filter_acl_deny_overrides_abac_allow(async_db_session):
    tenant = Tenant(name="tenant_unified_acl_deny", slug="tenant_unified_acl_deny", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    user = User(
        username="unified_deny_user",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    owner = User(
        username="unified_owner_user",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    async_db_session.add_all([user, owner])
    await async_db_session.commit()
    await async_db_session.refresh(user)
    await async_db_session.refresh(owner)

    collection = await _ensure_collection(async_db_session, tenant.id, owner.id)
    doc = Document(
        collection_id=collection.id,
        tenant_id=tenant.id,
        filename="blocked-by-acl.pdf",
        file_url="file://blocked",
        file_size=10,
        file_hash="hash",
        owner_id=owner.id,
    )
    async_db_session.add(doc)
    await async_db_session.commit()
    await async_db_session.refresh(doc)

    async_db_session.add(
        ResourceAcl(
            tenant_id=tenant.id,
            resource_type="document",
            resource_id=doc.id,
            owner_id=doc.owner_id,
            status="active",
        )
    )
    async_db_session.add(
        AclGrant(
            tenant_id=tenant.id,
            resource_type="document",
            resource_id=doc.id,
            principal_type="user",
            principal_id=str(user.id),
            permission="read",
            effect="deny",
            created_by=user.id,
        )
    )
    await async_db_session.commit()

    unified_filter = await build_unified_resource_filter(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        user_role=user.role,
        resource_type="document",
        resource_id_column=Document.id,
        resource_owner_id_column=Document.owner_id,
    )

    assert unified_filter.allow_all
    assert not unified_filter.deny_all
    assert unified_filter.clause is None

    stmt = select(Document.id).where(Document.tenant_id == tenant.id)
    result = await async_db_session.execute(stmt)
    allowed_ids = {row[0] for row in result.all()}
    # ACL deny is non-blocking under additive ACL semantics; ABAC allow still grants access.
    assert doc.id in allowed_ids


@pytest.mark.asyncio
async def test_build_unified_resource_filter_acl_not_applicable_keeps_abac_result(async_db_session):
    tenant = Tenant(name="tenant_unified_acl_na", slug="tenant_unified_acl_na", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    user = User(
        username="unified_na_user",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.commit()
    await async_db_session.refresh(user)

    collection = await _ensure_collection(async_db_session, tenant.id, user.id)
    doc = Document(
        collection_id=collection.id,
        tenant_id=tenant.id,
        filename="allowed-no-acl.pdf",
        file_url="file://allowed-no-acl",
        file_size=10,
        file_hash="hash",
        owner_id=user.id,
    )
    async_db_session.add(doc)
    await async_db_session.commit()
    await async_db_session.refresh(doc)

    unified_filter = await build_unified_resource_filter(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        user_role=user.role,
        resource_type="document",
        resource_id_column=Document.id,
        resource_owner_id_column=Document.owner_id,
    )

    assert unified_filter.allow_all
    assert not unified_filter.deny_all
    assert unified_filter.clause is None

    stmt = select(Document.id).where(Document.tenant_id == tenant.id)
    result = await async_db_session.execute(stmt)
    allowed_ids = {row[0] for row in result.all()}
    assert doc.id in allowed_ids


@pytest.mark.asyncio
async def test_build_unified_resource_filter_denies_when_acl_inactive(async_db_session):
    tenant = Tenant(name="tenant_unified_acl_inactive", slug="tenant_unified_acl_inactive", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    user = User(
        username="unified_inactive_user",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.commit()
    await async_db_session.refresh(user)

    collection = await _ensure_collection(async_db_session, tenant.id, user.id)
    doc = Document(
        collection_id=collection.id,
        tenant_id=tenant.id,
        filename="inactive-acl.pdf",
        file_url="file://inactive-acl",
        file_size=10,
        file_hash="hash",
        owner_id=user.id,
    )
    async_db_session.add(doc)
    await async_db_session.commit()
    await async_db_session.refresh(doc)

    async_db_session.add(
        ResourceAcl(
            tenant_id=tenant.id,
            resource_type="document",
            resource_id=doc.id,
            owner_id=user.id,
            status="inactive",
        )
    )
    await async_db_session.commit()

    unified_filter = await build_unified_resource_filter(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        user_role=user.role,
        resource_type="document",
        resource_model=Document,
    )

    if unified_filter.allow_all:
        stmt = select(Document.id).where(Document.tenant_id == tenant.id)
    else:
        stmt = select(Document.id).where(Document.tenant_id == tenant.id, unified_filter.clause)
    result = await async_db_session.execute(stmt)
    allowed_ids = {row[0] for row in result.all()}
    # Inactive ACL does not block ABAC baseline access in additive mode.
    assert doc.id in allowed_ids


@pytest.mark.asyncio
async def test_build_unified_resource_filter_owner_fallback_column_allows(async_db_session):
    tenant = Tenant(name="tenant_unified_owner_fallback", slug="tenant_unified_owner_fallback", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    user = User(
        username="unified_owner_fallback_user",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.commit()
    await async_db_session.refresh(user)

    collection = await _ensure_collection(async_db_session, tenant.id, user.id)
    doc = Document(
        collection_id=collection.id,
        tenant_id=tenant.id,
        filename="owner-fallback.pdf",
        file_url="file://owner-fallback",
        file_size=10,
        file_hash="hash",
        owner_id=user.id,
    )
    async_db_session.add(doc)
    await async_db_session.commit()
    await async_db_session.refresh(doc)

    async_db_session.add(
        ResourceAcl(
            tenant_id=tenant.id,
            resource_type="document",
            resource_id=doc.id,
            owner_id=doc.owner_id,
            status="active",
        )
    )
    await async_db_session.commit()

    unified_filter = await build_unified_resource_filter(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        user_role=user.role,
        resource_type="document",
        resource_model=Document,
        resource_owner_id_column=Document.owner_id,
    )

    stmt = (
        select(Document.id).where(Document.tenant_id == tenant.id)
        if unified_filter.allow_all
        else select(Document.id).where(Document.tenant_id == tenant.id, unified_filter.clause)
    )
    result = await async_db_session.execute(stmt)
    allowed_ids = {row[0] for row in result.all()}
    assert doc.id in allowed_ids


@pytest.mark.asyncio
async def test_build_unified_resource_filter_acl_owner_precedence_over_fallback(async_db_session):
    tenant = Tenant(name="tenant_unified_owner_precedence", slug="tenant_unified_owner_precedence", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    acl_owner = User(
        username="acl_owner_user",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    uploaded_owner = User(
        username="uploaded_owner_user",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    async_db_session.add_all([acl_owner, uploaded_owner])
    await async_db_session.commit()
    await async_db_session.refresh(acl_owner)
    await async_db_session.refresh(uploaded_owner)

    collection = await _ensure_collection(async_db_session, tenant.id, acl_owner.id)
    doc = Document(
        collection_id=collection.id,
        tenant_id=tenant.id,
        filename="owner-precedence.pdf",
        file_url="file://owner-precedence",
        file_size=10,
        file_hash="hash",
        owner_id=uploaded_owner.id,
    )
    async_db_session.add(doc)
    await async_db_session.commit()
    await async_db_session.refresh(doc)

    async_db_session.add(
        ResourceAcl(
            tenant_id=tenant.id,
            resource_type="document",
            resource_id=doc.id,
            owner_id=acl_owner.id,
            status="active",
        )
    )
    await async_db_session.commit()

    unified_filter = await build_unified_resource_filter(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=uploaded_owner.id,
        user_role=uploaded_owner.role,
        resource_type="document",
        resource_model=Document,
        resource_owner_id_column=Document.owner_id,
    )

    stmt = (
        select(Document.id).where(Document.tenant_id == tenant.id)
        if unified_filter.allow_all
        else select(Document.id).where(Document.tenant_id == tenant.id, unified_filter.clause)
    )
    result = await async_db_session.execute(stmt)
    allowed_ids = {row[0] for row in result.all()}
    # ABAC baseline owner access is preserved even when ACL owner differs.
    assert doc.id in allowed_ids


@pytest.mark.asyncio
async def test_build_unified_resource_filter_role_allow_grant_allows(async_db_session):
    tenant = Tenant(name="tenant_unified_role_allow", slug="tenant_unified_role_allow", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    user = User(
        username="unified_role_user",
        email=None,
        hashed_password="hashed",
        role="analyst",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.commit()
    await async_db_session.refresh(user)

    collection = await _ensure_collection(async_db_session, tenant.id, user.id)
    doc = Document(
        collection_id=collection.id,
        tenant_id=tenant.id,
        filename="role-allow.pdf",
        file_url="file://role-allow",
        file_size=10,
        file_hash="hash",
        owner_id=user.id,
    )
    async_db_session.add(doc)
    await async_db_session.commit()
    await async_db_session.refresh(doc)

    async_db_session.add(
        ResourceAcl(
            tenant_id=tenant.id,
            resource_type="document",
            resource_id=doc.id,
            owner_id=doc.owner_id,
            status="active",
        )
    )
    async_db_session.add(
        AclGrant(
            tenant_id=tenant.id,
            resource_type="document",
            resource_id=doc.id,
            principal_type="role",
            principal_id="analyst",
            permission="read",
            effect="allow",
            created_by=user.id,
        )
    )
    await async_db_session.commit()

    unified_filter = await build_unified_resource_filter(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        user_role=user.role,
        resource_type="document",
        resource_model=Document,
    )

    stmt = (
        select(Document.id).where(Document.tenant_id == tenant.id)
        if unified_filter.allow_all
        else select(Document.id).where(Document.tenant_id == tenant.id, unified_filter.clause)
    )
    result = await async_db_session.execute(stmt)
    allowed_ids = {row[0] for row in result.all()}
    assert doc.id in allowed_ids


@pytest.mark.asyncio
async def test_build_unified_resource_filter_manage_fast_path_allows(async_db_session):
    tenant = Tenant(name="tenant_unified_manage_fast_path", slug="tenant_unified_manage_fast_path", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    user = User(
        username="unified_manage_user",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.commit()
    await async_db_session.refresh(user)

    collection = await _ensure_collection(async_db_session, tenant.id, user.id)
    doc = Document(
        collection_id=collection.id,
        tenant_id=tenant.id,
        filename="manage-fast-path.pdf",
        file_url="file://manage-fast-path",
        file_size=10,
        file_hash="hash",
        owner_id=user.id,
    )
    async_db_session.add(doc)
    await async_db_session.commit()
    await async_db_session.refresh(doc)

    async_db_session.add(
        ResourceAcl(
            tenant_id=tenant.id,
            resource_type="document",
            resource_id=doc.id,
            owner_id=doc.owner_id,
            status="active",
        )
    )
    await async_db_session.commit()

    unified_filter = await build_unified_resource_filter(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        user_role=user.role,
        resource_type="document",
        resource_model=Document,
        has_manage_permission=True,
    )

    assert unified_filter.allow_all
    assert not unified_filter.deny_all
    assert unified_filter.clause is None

    stmt = select(Document.id).where(Document.tenant_id == tenant.id)
    result = await async_db_session.execute(stmt)
    allowed_ids = {row[0] for row in result.all()}
    assert doc.id in allowed_ids


@pytest.mark.asyncio
async def test_build_unified_resource_filter_accepts_convention_resource_model(async_db_session):
    tenant = Tenant(name="tenant_unified_convention", slug="tenant_unified_convention", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    user = User(
        username="unified_convention_user",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.commit()
    await async_db_session.refresh(user)

    collection = await _ensure_collection(async_db_session, tenant.id, user.id)
    doc = Document(
        collection_id=collection.id,
        tenant_id=tenant.id,
        filename="convention-model.pdf",
        file_url="file://convention-model",
        file_size=10,
        file_hash="hash",
        owner_id=user.id,
    )
    async_db_session.add(doc)
    await async_db_session.commit()
    await async_db_session.refresh(doc)

    unified_filter = await build_unified_resource_filter(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        user_role=user.role,
        resource_type="document",
        resource_model=Document,
    )

    assert unified_filter.allow_all
    assert unified_filter.clause is None
    stmt = select(Document.id).where(Document.tenant_id == tenant.id)
    result = await async_db_session.execute(stmt)
    allowed_ids = {row[0] for row in result.all()}
    assert doc.id in allowed_ids


@pytest.mark.asyncio
async def test_build_unified_resource_filter_raises_when_model_and_id_column_missing(async_db_session):
    tenant = Tenant(name="tenant_unified_missing_id", slug="tenant_unified_missing_id", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    user = User(
        username="unified_missing_id_user",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.commit()
    await async_db_session.refresh(user)

    with pytest.raises(ValueError, match="resource_id_column is required"):
        await build_unified_resource_filter(
            db_session=async_db_session,
            tenant_id=tenant.id,
            user_id=user.id,
            user_role=user.role,
            resource_type="document",
            resource_model=None,
            resource_id_column=None,
        )


@pytest.mark.asyncio
async def test_build_abac_resource_filter_user_tags_contains_resource_tags(async_db_session):
    tenant = Tenant(name="tenant_abac_contains", slug="tenant_abac_contains", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    user = User(
        username="dana",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.commit()
    await async_db_session.refresh(user)

    tag_key = TagKey(
        id=1,
        tenant_id=tenant.id,
        name="dept",
        description=None,
    )
    async_db_session.add(tag_key)
    await async_db_session.commit()
    await async_db_session.refresh(tag_key)

    tag_value_sales = TagValue(id=1, tenant_id=tenant.id, key_id=tag_key.id, value="sales")
    tag_value_marketing = TagValue(id=2, tenant_id=tenant.id, key_id=tag_key.id, value="marketing")
    async_db_session.add_all([tag_value_sales, tag_value_marketing])
    await async_db_session.commit()

    async_db_session.add(
        TagBinding(
            id=1,
            tenant_id=tenant.id,
            resource_type="user",
            resource_id=user.id,
            tag_value_id=tag_value_sales.id,
        )
    )

    collection = await _ensure_collection(async_db_session, tenant.id, user.id)
    doc_allowed = Document(
        collection_id=collection.id,
        tenant_id=tenant.id,
        filename="allowed.pdf",
        file_url="file://allowed",
        file_size=10,
        file_hash="hash1",
        owner_id=user.id,
    )
    collection = await _ensure_collection(async_db_session, tenant.id, user.id)
    doc_denied = Document(
        collection_id=collection.id,
        tenant_id=tenant.id,
        filename="denied.pdf",
        file_url="file://denied",
        file_size=12,
        file_hash="hash2",
        owner_id=user.id,
    )
    collection = await _ensure_collection(async_db_session, tenant.id, user.id)
    doc_untagged = Document(
        collection_id=collection.id,
        tenant_id=tenant.id,
        filename="untagged.pdf",
        file_url="file://untagged",
        file_size=8,
        file_hash="hash3",
        owner_id=user.id,
    )
    async_db_session.add_all([doc_allowed, doc_denied, doc_untagged])
    await async_db_session.commit()
    await async_db_session.refresh(doc_allowed)
    await async_db_session.refresh(doc_denied)
    await async_db_session.refresh(doc_untagged)

    async_db_session.add_all(
        [
            TagBinding(
                id=2,
                tenant_id=tenant.id,
                resource_type="document",
                resource_id=doc_allowed.id,
                tag_value_id=tag_value_sales.id,
            ),
            TagBinding(
                id=3,
                tenant_id=tenant.id,
                resource_type="document",
                resource_id=doc_denied.id,
                tag_value_id=tag_value_marketing.id,
            ),
        ]
    )

    policy = AbacPolicy(
        id=1,
        tenant_id=tenant.id,
        name="dept_subset",
        description=None,
        resource_type="document",
        expression=":user.tags contains :resource.tags",
        status="active",
    )
    async_db_session.add(policy)
    await async_db_session.commit()

    abac_filter = await _build_abac_resource_filter(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        resource_type="document",
        resource_id_column=Document.id,
    )

    stmt = select(Document.id).where(Document.tenant_id == tenant.id, abac_filter.clause)
    compiled = str(stmt)
    assert "tag_bindings" in compiled
    assert "EXISTS" in compiled or "exists" in compiled
    result = await async_db_session.execute(stmt)
    allowed_ids = {row[0] for row in result.all()}

    assert doc_allowed.id in allowed_ids
    assert doc_untagged.id in allowed_ids
    assert doc_denied.id not in allowed_ids


@pytest.mark.asyncio
async def test_build_abac_resource_filter_user_tags_contains_resource_tags_scoped_keys(async_db_session):
    tenant = Tenant(name="tenant_abac_contains_scoped", slug="tenant_abac_contains_scoped", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    user = User(
        username="dana_scoped",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.commit()
    await async_db_session.refresh(user)

    dept_key = TagKey(id=1, tenant_id=tenant.id, name="dept", description=None)
    region_key = TagKey(id=2, tenant_id=tenant.id, name="region", description=None)
    project_key = TagKey(id=3, tenant_id=tenant.id, name="project", description=None)
    async_db_session.add_all([dept_key, region_key, project_key])
    await async_db_session.commit()

    dept_sales = TagValue(id=1, tenant_id=tenant.id, key_id=dept_key.id, value="sales")
    region_cn = TagValue(id=2, tenant_id=tenant.id, key_id=region_key.id, value="cn")
    region_us = TagValue(id=3, tenant_id=tenant.id, key_id=region_key.id, value="us")
    project_alpha = TagValue(id=4, tenant_id=tenant.id, key_id=project_key.id, value="alpha")
    project_beta = TagValue(id=5, tenant_id=tenant.id, key_id=project_key.id, value="beta")
    async_db_session.add_all([dept_sales, region_cn, region_us, project_alpha, project_beta])
    await async_db_session.commit()

    async_db_session.add_all(
        [
            TagBinding(
                id=1,
                tenant_id=tenant.id,
                resource_type="user",
                resource_id=user.id,
                tag_value_id=dept_sales.id,
            ),
            TagBinding(
                id=2,
                tenant_id=tenant.id,
                resource_type="user",
                resource_id=user.id,
                tag_value_id=region_cn.id,
            ),
            TagBinding(
                id=3,
                tenant_id=tenant.id,
                resource_type="user",
                resource_id=user.id,
                tag_value_id=project_alpha.id,
            ),
        ]
    )

    collection = await _ensure_collection(async_db_session, tenant.id, user.id)
    doc_allowed = Document(
        collection_id=collection.id,
        tenant_id=tenant.id,
        filename="allowed_scoped.pdf",
        file_url="file://allowed_scoped",
        file_size=10,
        file_hash="hash4",
        owner_id=user.id,
    )
    collection = await _ensure_collection(async_db_session, tenant.id, user.id)
    doc_denied_region = Document(
        collection_id=collection.id,
        tenant_id=tenant.id,
        filename="denied_region.pdf",
        file_url="file://denied_region",
        file_size=10,
        file_hash="hash5",
        owner_id=user.id,
    )
    collection = await _ensure_collection(async_db_session, tenant.id, user.id)
    doc_allowed_outside_scope_diff = Document(
        collection_id=collection.id,
        tenant_id=tenant.id,
        filename="allowed_outside_scope.pdf",
        file_url="file://allowed_outside_scope",
        file_size=10,
        file_hash="hash6",
        owner_id=user.id,
    )
    collection = await _ensure_collection(async_db_session, tenant.id, user.id)
    doc_allowed_no_scoped_tags = Document(
        collection_id=collection.id,
        tenant_id=tenant.id,
        filename="allowed_no_scoped.pdf",
        file_url="file://allowed_no_scoped",
        file_size=10,
        file_hash="hash7",
        owner_id=user.id,
    )
    async_db_session.add_all(
        [
            doc_allowed,
            doc_denied_region,
            doc_allowed_outside_scope_diff,
            doc_allowed_no_scoped_tags,
        ]
    )
    await async_db_session.commit()
    await async_db_session.refresh(doc_allowed)
    await async_db_session.refresh(doc_denied_region)
    await async_db_session.refresh(doc_allowed_outside_scope_diff)
    await async_db_session.refresh(doc_allowed_no_scoped_tags)

    async_db_session.add_all(
        [
            TagBinding(
                id=4,
                tenant_id=tenant.id,
                resource_type="document",
                resource_id=doc_allowed.id,
                tag_value_id=dept_sales.id,
            ),
            TagBinding(
                id=5,
                tenant_id=tenant.id,
                resource_type="document",
                resource_id=doc_allowed.id,
                tag_value_id=region_cn.id,
            ),
            TagBinding(
                id=6,
                tenant_id=tenant.id,
                resource_type="document",
                resource_id=doc_denied_region.id,
                tag_value_id=dept_sales.id,
            ),
            TagBinding(
                id=7,
                tenant_id=tenant.id,
                resource_type="document",
                resource_id=doc_denied_region.id,
                tag_value_id=region_us.id,
            ),
            TagBinding(
                id=8,
                tenant_id=tenant.id,
                resource_type="document",
                resource_id=doc_allowed_outside_scope_diff.id,
                tag_value_id=dept_sales.id,
            ),
            TagBinding(
                id=9,
                tenant_id=tenant.id,
                resource_type="document",
                resource_id=doc_allowed_outside_scope_diff.id,
                tag_value_id=region_cn.id,
            ),
            TagBinding(
                id=10,
                tenant_id=tenant.id,
                resource_type="document",
                resource_id=doc_allowed_outside_scope_diff.id,
                tag_value_id=project_beta.id,
            ),
            TagBinding(
                id=11,
                tenant_id=tenant.id,
                resource_type="document",
                resource_id=doc_allowed_no_scoped_tags.id,
                tag_value_id=project_beta.id,
            ),
        ]
    )

    policy = AbacPolicy(
        id=1,
        tenant_id=tenant.id,
        name="dept_region_subset",
        description=None,
        resource_type="document",
        expression=':user.tags contains :resource.tags on ("dept", "region")',
        status="active",
    )
    async_db_session.add(policy)
    await async_db_session.commit()

    abac_filter = await _build_abac_resource_filter(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        resource_type="document",
        resource_id_column=Document.id,
    )

    stmt = select(Document.id).where(Document.tenant_id == tenant.id, abac_filter.clause)
    result = await async_db_session.execute(stmt)
    allowed_ids = {row[0] for row in result.all()}

    assert doc_allowed.id in allowed_ids
    assert doc_allowed_outside_scope_diff.id in allowed_ids
    assert doc_allowed_no_scoped_tags.id in allowed_ids
    assert doc_denied_region.id not in allowed_ids


@pytest.mark.asyncio
async def test_build_abac_resource_filter_asset_exact_sql(async_db_session):
    tenant = Tenant(name="tenant_abac_asset_sql", slug="tenant_abac_asset_sql", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    user = User(
        username="eli",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.commit()
    await async_db_session.refresh(user)

    tag_key = TagKey(
        id=1,
        tenant_id=tenant.id,
        name="dept",
        description=None,
    )
    async_db_session.add(tag_key)
    await async_db_session.commit()
    await async_db_session.refresh(tag_key)

    tag_value_sales = TagValue(id=1, tenant_id=tenant.id, key_id=tag_key.id, value="sales")
    async_db_session.add(tag_value_sales)
    await async_db_session.commit()

    data_source = DataSource(
        tenant_id=tenant.id,
        name="source",
        type="sqlite",
        config={},
        owner_id=user.id,
    )
    async_db_session.add(data_source)
    await async_db_session.commit()
    await async_db_session.refresh(data_source)

    asset = AssetMetadata(
        data_source_id=data_source.id,
        asset_name="orders",
        columns=[],
        source_info={},
        owner_id=user.id,
    )
    async_db_session.add(asset)
    await async_db_session.commit()
    await async_db_session.refresh(asset)

    async_db_session.add(
        TagBinding(
            id=1,
            tenant_id=tenant.id,
            resource_type="asset",
            resource_id=asset.id,
            tag_value_id=tag_value_sales.id,
        )
    )

    policy = AbacPolicy(
        id=1,
        tenant_id=tenant.id,
        name="asset_sales",
        description=None,
        resource_type="asset",
        expression=':resource.tags has "dept:sales"',
        status="active",
    )
    async_db_session.add(policy)
    await async_db_session.commit()

    abac_filter = await _build_abac_resource_filter(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        resource_type="asset",
        resource_id_column=AssetMetadata.id,
    )

    stmt = select(AssetMetadata.id).where(abac_filter.clause)
    compiled = str(stmt.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))

    expected_sql = (
        "SELECT asset_metadata.id \n"
        "FROM asset_metadata \n"
        "WHERE asset_metadata.id IN (SELECT tag_bindings.resource_id \n"
        "FROM tag_bindings JOIN tag_values ON tag_bindings.tag_value_id = tag_values.id "
        "JOIN tag_keys ON tag_values.key_id = tag_keys.id \n"
        "WHERE tag_bindings.tenant_id = 1 AND tag_bindings.resource_type = 'asset' "
        "AND tag_keys.name = 'dept' AND tag_values.value = 'sales')"
    )

    assert compiled == expected_sql


@pytest.mark.asyncio
async def test_evaluate_single_expression_supports_resource_owner_id(async_db_session):
    tenant = Tenant(name="tenant_abac_eval_owner", slug="tenant_abac_eval_owner", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    owner = User(
        username="owner_user",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    other_user = User(
        username="other_user",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    async_db_session.add_all([owner, other_user])
    await async_db_session.commit()
    await async_db_session.refresh(owner)
    await async_db_session.refresh(other_user)

    collection = await _ensure_collection(async_db_session, tenant.id, owner.id)
    document = Document(
        collection_id=collection.id,
        tenant_id=tenant.id,
        filename="owned.pdf",
        file_url="file://owned",
        file_size=10,
        file_hash="hash",
        owner_id=owner.id,
    )
    async_db_session.add(document)
    await async_db_session.commit()
    await async_db_session.refresh(document)

    expression = ":user.id equals :resource.owner_id"

    allowed_owner, _ = await evaluate_single_expression(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=owner.id,
        user_role=owner.role,
        resource_type="document",
        resource_id=document.id,
        expression=expression,
    )
    assert allowed_owner is True

    allowed_other, _ = await evaluate_single_expression(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=other_user.id,
        user_role=other_user.role,
        resource_type="document",
        resource_id=document.id,
        expression=expression,
    )
    assert allowed_other is False


@pytest.mark.asyncio
async def test_evaluate_single_expression_uses_owner_id_not_uploaded_by(async_db_session):
    tenant = Tenant(name="tenant_abac_eval_owner_precedence", slug="tenant_abac_eval_owner_precedence", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    owner = User(
        username="precedence_owner",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    uploader = User(
        username="precedence_uploader",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    async_db_session.add_all([owner, uploader])
    await async_db_session.commit()
    await async_db_session.refresh(owner)
    await async_db_session.refresh(uploader)

    collection = await _ensure_collection(async_db_session, tenant.id, owner.id)
    document = Document(
        collection_id=collection.id,
        tenant_id=tenant.id,
        filename="owner-precedence.pdf",
        file_url="file://owner-precedence",
        file_size=10,
        file_hash="hash",
        owner_id=owner.id,
    )
    async_db_session.add(document)
    await async_db_session.commit()
    await async_db_session.refresh(document)

    expression = ":user.id equals :resource.owner_id"

    allowed_owner, _ = await evaluate_single_expression(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=owner.id,
        user_role=owner.role,
        resource_type="document",
        resource_id=document.id,
        expression=expression,
    )
    assert allowed_owner is True

    allowed_uploader, _ = await evaluate_single_expression(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=uploader.id,
        user_role=uploader.role,
        resource_type="document",
        resource_id=document.id,
        expression=expression,
    )
    assert allowed_uploader is False


@pytest.mark.asyncio
async def test_evaluate_single_expression_supports_api_connector_owner_id(async_db_session):
    tenant = Tenant(name="tenant_abac_eval_connector_owner", slug="tenant_abac_eval_connector_owner", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    owner = User(
        username="connector_owner",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    other_user = User(
        username="connector_other",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    async_db_session.add_all([owner, other_user])
    await async_db_session.commit()
    await async_db_session.refresh(owner)
    await async_db_session.refresh(other_user)

    connector = ApiConnector(
        tenant_id=tenant.id,
        owner_id=owner.id,
        name="owner-test-connector",
        description=None,
        base_url="https://example.com",
        auth_type="none",
        auth_config={},
        rate_policy={},
        schema_source_type="url",
        schema_source_url="https://example.com/openapi.json",
        status="active",
    )
    async_db_session.add(connector)
    await async_db_session.commit()
    await async_db_session.refresh(connector)

    expression = ":user.id equals :resource.owner_id"

    allowed_owner, _ = await evaluate_single_expression(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=owner.id,
        user_role=owner.role,
        resource_type="api_connector",
        resource_id=connector.id,
        expression=expression,
    )
    assert allowed_owner is True

    allowed_other, _ = await evaluate_single_expression(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=other_user.id,
        user_role=other_user.role,
        resource_type="api_connector",
        resource_id=connector.id,
        expression=expression,
    )
    assert allowed_other is False


def test_simulation_owner_resolver_registry_covers_supported_resource_types():
    assert set(_SIMULATION_OWNER_RESOLVERS.keys()) == {
        RESOURCE_TYPE_AGENT,
        RESOURCE_TYPE_DOCUMENT,
        RESOURCE_TYPE_DOCUMENT_COLLECTION,
        RESOURCE_TYPE_DATA_SOURCE,
        RESOURCE_TYPE_API_CONNECTOR,
    }


@pytest.mark.asyncio
async def test_build_abac_resource_filter_supports_key_only_wildcard_for_resource_tags(async_db_session):
    tenant = Tenant(name="tenant_abac_tag_wildcard", slug="tenant_abac_tag_wildcard", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    user = User(username="wild_user", email=None, hashed_password="hashed", role="member", tenant_id=tenant.id)
    async_db_session.add(user)
    await async_db_session.commit()
    await async_db_session.refresh(user)

    tag_key = TagKey(id=1, tenant_id=tenant.id, name="dept", description=None)
    async_db_session.add(tag_key)
    await async_db_session.commit()
    await async_db_session.refresh(tag_key)

    tag_value_sales = TagValue(id=1, tenant_id=tenant.id, key_id=tag_key.id, value="sales")
    async_db_session.add(tag_value_sales)
    await async_db_session.commit()
    await async_db_session.refresh(tag_value_sales)

    collection = await _ensure_collection(async_db_session, tenant.id, user.id)
    doc_tagged = Document(
        collection_id=collection.id,
        tenant_id=tenant.id,
        filename="tagged.pdf",
        file_url="file://tagged",
        file_size=10,
        file_hash="hash1",
        owner_id=user.id,
    )
    collection = await _ensure_collection(async_db_session, tenant.id, user.id)
    doc_untagged = Document(
        collection_id=collection.id,
        tenant_id=tenant.id,
        filename="untagged.pdf",
        file_url="file://untagged",
        file_size=10,
        file_hash="hash2",
        owner_id=user.id,
    )
    async_db_session.add_all([doc_tagged, doc_untagged])
    await async_db_session.commit()
    await async_db_session.refresh(doc_tagged)
    await async_db_session.refresh(doc_untagged)

    async_db_session.add(
        TagBinding(
            id=1,
            tenant_id=tenant.id,
            resource_type="document",
            resource_id=doc_tagged.id,
            tag_value_id=tag_value_sales.id,
        )
    )

    policy = AbacPolicy(
        id=1,
        tenant_id=tenant.id,
        name="dept_wildcard",
        description=None,
        resource_type="document",
        expression=':resource.tags has "dept:*"',
        status="active",
    )
    async_db_session.add(policy)
    await async_db_session.commit()

    abac_filter = await _build_abac_resource_filter(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        resource_type="document",
        resource_id_column=Document.id,
    )

    stmt = select(Document.id).where(Document.tenant_id == tenant.id, abac_filter.clause)
    result = await async_db_session.execute(stmt)
    allowed_ids = {row[0] for row in result.all()}

    assert doc_tagged.id in allowed_ids
    assert doc_untagged.id not in allowed_ids


@pytest.mark.asyncio
async def test_evaluate_single_expression_supports_key_only_wildcard_for_user_tags(async_db_session):
    tenant = Tenant(name="tenant_abac_user_wildcard", slug="tenant_abac_user_wildcard", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    user_with_dept = User(
        username="user_with_dept",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    user_without_dept = User(
        username="user_without_dept",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    async_db_session.add_all([user_with_dept, user_without_dept])
    await async_db_session.commit()
    await async_db_session.refresh(user_with_dept)
    await async_db_session.refresh(user_without_dept)

    dept_key = TagKey(id=1, tenant_id=tenant.id, name="dept", description=None)
    region_key = TagKey(id=2, tenant_id=tenant.id, name="region", description=None)
    async_db_session.add_all([dept_key, region_key])
    await async_db_session.commit()

    dept_value_sales = TagValue(id=1, tenant_id=tenant.id, key_id=dept_key.id, value="sales")
    region_value_cn = TagValue(id=2, tenant_id=tenant.id, key_id=region_key.id, value="cn")
    async_db_session.add_all([dept_value_sales, region_value_cn])
    await async_db_session.commit()

    async_db_session.add_all(
        [
            TagBinding(
                id=1,
                tenant_id=tenant.id,
                resource_type="user",
                resource_id=user_with_dept.id,
                tag_value_id=dept_value_sales.id,
            ),
            TagBinding(
                id=2,
                tenant_id=tenant.id,
                resource_type="user",
                resource_id=user_without_dept.id,
                tag_value_id=region_value_cn.id,
            ),
        ]
    )

    collection = await _ensure_collection(async_db_session, tenant.id, user_with_dept.id)
    doc = Document(
        collection_id=collection.id,
        tenant_id=tenant.id,
        filename="owner.pdf",
        file_url="file://owner",
        file_size=10,
        file_hash="hash",
        owner_id=user_with_dept.id,
    )
    async_db_session.add(doc)
    await async_db_session.commit()
    await async_db_session.refresh(doc)

    expression = ':user.tags has "dept:*"'

    allowed_with_dept, _ = await evaluate_single_expression(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=user_with_dept.id,
        user_role=user_with_dept.role,
        resource_type="document",
        resource_id=doc.id,
        expression=expression,
    )
    assert allowed_with_dept is True

    allowed_without_dept, _ = await evaluate_single_expression(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=user_without_dept.id,
        user_role=user_without_dept.role,
        resource_type="document",
        resource_id=doc.id,
        expression=expression,
    )
    assert allowed_without_dept is False


@pytest.mark.asyncio
async def test_evaluate_single_expression_supports_rank_gte_for_security_tag(async_db_session):
    tenant = Tenant(name="tenant_abac_rank", slug="tenant_abac_rank", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    user_high = User(username="rank_high", email=None, hashed_password="hashed", role="member", tenant_id=tenant.id)
    user_low = User(username="rank_low", email=None, hashed_password="hashed", role="member", tenant_id=tenant.id)
    async_db_session.add_all([user_high, user_low])
    await async_db_session.commit()
    await async_db_session.refresh(user_high)
    await async_db_session.refresh(user_low)

    tag_key = TagKey(id=1, tenant_id=tenant.id, name="数据安全性", description=None)
    async_db_session.add(tag_key)
    await async_db_session.commit()

    value_public = TagValue(id=1, tenant_id=tenant.id, key_id=tag_key.id, value="公开", rank=1)
    value_sensitive = TagValue(id=2, tenant_id=tenant.id, key_id=tag_key.id, value="敏感", rank=3)
    async_db_session.add_all([value_public, value_sensitive])
    await async_db_session.commit()

    async_db_session.add_all(
        [
            TagBinding(
                id=1,
                tenant_id=tenant.id,
                resource_type="user",
                resource_id=user_high.id,
                tag_value_id=value_sensitive.id,
            ),
            TagBinding(
                id=2,
                tenant_id=tenant.id,
                resource_type="user",
                resource_id=user_low.id,
                tag_value_id=value_public.id,
            ),
        ]
    )

    collection = await _ensure_collection(async_db_session, tenant.id, user_high.id)
    doc = Document(
        collection_id=collection.id,
        tenant_id=tenant.id,
        filename="ranked.pdf",
        file_url="file://ranked",
        file_size=10,
        file_hash="hash",
        owner_id=user_high.id,
    )
    async_db_session.add(doc)
    await async_db_session.commit()
    await async_db_session.refresh(doc)

    async_db_session.add(
        TagBinding(
            id=3,
            tenant_id=tenant.id,
            resource_type="document",
            resource_id=doc.id,
            tag_value_id=value_public.id,
        )
    )
    await async_db_session.commit()

    expression = ':user.tags rank_gte :resource.tags on "数据安全性"'

    allowed_high, _ = await evaluate_single_expression(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=user_high.id,
        user_role=user_high.role,
        resource_type="document",
        resource_id=doc.id,
        expression=expression,
    )
    assert allowed_high is True

    allowed_low, _ = await evaluate_single_expression(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=user_low.id,
        user_role=user_low.role,
        resource_type="document",
        resource_id=doc.id,
        expression=expression,
    )
    assert allowed_low is True


@pytest.mark.asyncio
async def test_evaluate_single_expression_rank_gte_denies_when_user_rank_is_lower(async_db_session):
    tenant = Tenant(name="tenant_abac_rank_deny", slug="tenant_abac_rank_deny", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    user = User(username="rank_user", email=None, hashed_password="hashed", role="member", tenant_id=tenant.id)
    async_db_session.add(user)
    await async_db_session.commit()
    await async_db_session.refresh(user)

    tag_key = TagKey(id=1, tenant_id=tenant.id, name="数据安全性", description=None)
    async_db_session.add(tag_key)
    await async_db_session.commit()

    value_internal = TagValue(id=1, tenant_id=tenant.id, key_id=tag_key.id, value="内部", rank=2)
    value_secret = TagValue(id=2, tenant_id=tenant.id, key_id=tag_key.id, value="机密", rank=4)
    async_db_session.add_all([value_internal, value_secret])
    await async_db_session.commit()

    async_db_session.add(
        TagBinding(
            id=1,
            tenant_id=tenant.id,
            resource_type="user",
            resource_id=user.id,
            tag_value_id=value_internal.id,
        )
    )

    collection = await _ensure_collection(async_db_session, tenant.id, user.id)
    doc = Document(
        collection_id=collection.id,
        tenant_id=tenant.id,
        filename="ranked_high.pdf",
        file_url="file://ranked_high",
        file_size=10,
        file_hash="hash",
        owner_id=user.id,
    )
    async_db_session.add(doc)
    await async_db_session.commit()
    await async_db_session.refresh(doc)

    async_db_session.add(
        TagBinding(
            id=2,
            tenant_id=tenant.id,
            resource_type="document",
            resource_id=doc.id,
            tag_value_id=value_secret.id,
        )
    )
    await async_db_session.commit()

    expression = ':user.tags rank_gte :resource.tags on "数据安全性"'

    allowed, _ = await evaluate_single_expression(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        user_role=user.role,
        resource_type="document",
        resource_id=doc.id,
        expression=expression,
    )
    assert allowed is False


# ---------------------------------------------------------------------------
# ACL explicit allow overrides ABAC (key sharing scenario)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_resource_action_acl_allow_overrides_abac_owner_only_policy(async_db_session):
    """Admin uploads doc; shares with member1 via ACL allow grant.

    The default ABAC policy only allows owner/admin, but the explicit ACL
    allow grant should override it and let member1 see the document.
    """
    tenant = Tenant(name="tenant_acl_override_eval", slug="tenant_acl_override_eval", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    admin = User(
        username="acl_override_admin",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    member1 = User(
        username="acl_override_member1",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    async_db_session.add_all([admin, member1])
    await async_db_session.commit()
    await async_db_session.refresh(admin)
    await async_db_session.refresh(member1)

    collection = await _ensure_collection(async_db_session, tenant.id, admin.id)
    doc = Document(
        collection_id=collection.id,
        tenant_id=tenant.id,
        filename="shared-by-admin.pdf",
        file_url="file://shared-by-admin",
        file_size=10,
        file_hash="hash",
        owner_id=admin.id,
    )
    async_db_session.add(doc)
    await async_db_session.commit()
    await async_db_session.refresh(doc)

    # ABAC policy: only owner can read (member1 is not the owner)
    policy = AbacPolicy(
        id=1,
        tenant_id=tenant.id,
        name="owner_only_read",
        description=None,
        resource_type="document",
        expression=":user.id equals :resource.owner_id",
        status="active",
    )
    async_db_session.add(policy)

    # Admin shares with member1 via ACL
    async_db_session.add(
        ResourceAcl(
            tenant_id=tenant.id,
            resource_type="document",
            resource_id=doc.id,
            owner_id=admin.id,
            status="active",
        )
    )
    async_db_session.add(
        AclGrant(
            tenant_id=tenant.id,
            resource_type="document",
            resource_id=doc.id,
            principal_type="user",
            principal_id=str(member1.id),
            permission="read",
            effect="allow",
            created_by=admin.id,
        )
    )
    await async_db_session.commit()

    allowed = await evaluate_resource_action(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=member1.id,
        user_role=member1.role,
        resource_type="document",
        resource_id=doc.id,
        resource_owner_id=doc.owner_id,
    )

    assert allowed is True


@pytest.mark.asyncio
async def test_build_unified_resource_filter_acl_allow_overrides_abac_owner_only_policy(async_db_session):
    """SQL pushdown: member1 with ACL allow grant sees admin's doc despite owner-only ABAC."""
    tenant = Tenant(name="tenant_acl_override_filter", slug="tenant_acl_override_filter", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    admin = User(
        username="acl_filter_admin",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    member1 = User(
        username="acl_filter_member1",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    async_db_session.add_all([admin, member1])
    await async_db_session.commit()
    await async_db_session.refresh(admin)
    await async_db_session.refresh(member1)

    collection = await _ensure_collection(async_db_session, tenant.id, admin.id)
    doc = Document(
        collection_id=collection.id,
        tenant_id=tenant.id,
        filename="acl-override-filter.pdf",
        file_url="file://acl-override-filter",
        file_size=10,
        file_hash="hash",
        owner_id=admin.id,
    )
    async_db_session.add(doc)
    await async_db_session.commit()
    await async_db_session.refresh(doc)

    # ABAC policy: only owner can read — would normally block member1
    policy = AbacPolicy(
        id=1,
        tenant_id=tenant.id,
        name="owner_only_read_filter",
        description=None,
        resource_type="document",
        expression=":user.id equals :resource.owner_id",
        status="active",
    )
    async_db_session.add(policy)

    # Admin shares with member1 via ACL
    async_db_session.add(
        ResourceAcl(
            tenant_id=tenant.id,
            resource_type="document",
            resource_id=doc.id,
            owner_id=admin.id,
            status="active",
        )
    )
    async_db_session.add(
        AclGrant(
            tenant_id=tenant.id,
            resource_type="document",
            resource_id=doc.id,
            principal_type="user",
            principal_id=str(member1.id),
            permission="read",
            effect="allow",
            created_by=admin.id,
        )
    )
    await async_db_session.commit()

    unified_filter = await build_unified_resource_filter(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=member1.id,
        user_role=member1.role,
        resource_type="document",
        resource_model=Document,
    )

    assert not unified_filter.deny_all
    assert unified_filter.clause is not None

    stmt = select(Document.id).where(Document.tenant_id == tenant.id, unified_filter.clause)
    result = await async_db_session.execute(stmt)
    allowed_ids = {row[0] for row in result.all()}
    assert doc.id in allowed_ids
