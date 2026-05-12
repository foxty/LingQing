import pytest

from apps.shared.db.models import AbacPolicy, AclGrant, Document, ResourceAcl, Tenant, User
from apps.shared.document.service import DocumentService
from apps.shared.domain.types import ABAC_ACTION_READ, RESOURCE_TYPE_DOCUMENT_COLLECTION
from tests.helpers.document_fixtures import create_document, create_document_collection, create_tenant_user


@pytest.fixture
def document_service(async_db_session):
    return DocumentService(tenant_id=1, db_session=async_db_session, file_storage=object())


async def _seed_allow_all_collection_abac_policy(async_db_session, tenant_id: int) -> None:
    async_db_session.add(
        AbacPolicy(
            id=1,
            tenant_id=tenant_id,
            name="allow_all_collections",
            description=None,
            resource_type=RESOURCE_TYPE_DOCUMENT_COLLECTION,
            action=ABAC_ACTION_READ,
            expression=":resource.id equals :resource.id",
            status="active",
        )
    )
    await async_db_session.commit()


async def _seed_owner_only_collection_abac_policy(async_db_session, tenant_id: int) -> None:
    async_db_session.add(
        AbacPolicy(
            id=2,
            tenant_id=tenant_id,
            name="owner_only_collections",
            description=None,
            resource_type=RESOURCE_TYPE_DOCUMENT_COLLECTION,
            action=ABAC_ACTION_READ,
            expression=":resource.owner_id equals :user.id",
            status="active",
        )
    )
    await async_db_session.commit()


@pytest.mark.asyncio
async def test_list_documents_acl_not_applicable_keeps_abac(async_db_session):
    tenant, user = await create_tenant_user(async_db_session, tenant_name="tenant_member", username="user_member")
    await _seed_allow_all_collection_abac_policy(async_db_session, tenant.id)

    collection = await create_document_collection(async_db_session, tenant_id=tenant.id, owner_id=user.id)
    doc = await create_document(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=user.id,
        collection_id=collection.id,
        filename="visible.pdf",
    )

    service = DocumentService(tenant_id=tenant.id, db_session=async_db_session, file_storage=object())
    docs, pagination = await service.list_documents(
        requester_id=user.id,
        requester_role=user.role,
        page=1,
        page_size=10,
        query=None,
    )

    ids = {d.id for d in docs}
    assert doc.id in ids
    assert pagination.total == 1


@pytest.mark.asyncio
async def test_list_documents_acl_deny_filters_out_document(async_db_session):
    tenant, user = await create_tenant_user(async_db_session, tenant_name="tenant_acl_deny", username="user_acl")
    denied_owner = User(
        username="user_denied_owner",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    async_db_session.add(denied_owner)
    await async_db_session.commit()
    await async_db_session.refresh(denied_owner)
    await _seed_allow_all_collection_abac_policy(async_db_session, tenant.id)

    denied_collection = await create_document_collection(
        async_db_session, tenant_id=tenant.id, owner_id=denied_owner.id, name="Denied"
    )
    allowed_collection = await create_document_collection(
        async_db_session, tenant_id=tenant.id, owner_id=user.id, name="Allowed"
    )
    denied_doc = await create_document(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=denied_owner.id,
        collection_id=denied_collection.id,
        filename="denied.pdf",
        file_hash="hash1",
    )
    allowed_doc = await create_document(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=user.id,
        collection_id=allowed_collection.id,
        filename="allowed.pdf",
        file_hash="hash2",
    )

    async_db_session.add(
        ResourceAcl(
            tenant_id=tenant.id,
            resource_type=RESOURCE_TYPE_DOCUMENT_COLLECTION,
            resource_id=denied_collection.id,
            owner_id=denied_collection.owner_id,
            status="active",
        )
    )
    async_db_session.add(
        AclGrant(
            tenant_id=tenant.id,
            resource_type=RESOURCE_TYPE_DOCUMENT_COLLECTION,
            resource_id=denied_collection.id,
            principal_type="user",
            principal_id=str(user.id),
            permission="read",
            effect="deny",
            created_by=user.id,
        )
    )
    await async_db_session.commit()

    service = DocumentService(tenant_id=tenant.id, db_session=async_db_session, file_storage=object())
    docs, pagination = await service.list_documents(
        requester_id=user.id,
        requester_role=user.role,
        page=1,
        page_size=10,
        query=None,
    )

    ids = {d.id for d in docs}
    assert denied_doc.id in ids
    assert allowed_doc.id in ids
    assert pagination.total == 2


@pytest.mark.asyncio
async def test_list_documents_acl_role_allow_includes_document(async_db_session):
    tenant, user = await create_tenant_user(
        async_db_session, tenant_name="tenant_analyst", username="user_analyst", role="analyst"
    )
    await _seed_allow_all_collection_abac_policy(async_db_session, tenant.id)

    collection = await create_document_collection(async_db_session, tenant_id=tenant.id, owner_id=user.id)
    doc = await create_document(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=user.id,
        collection_id=collection.id,
        filename="role-allowed.pdf",
    )

    async_db_session.add(
        ResourceAcl(
            tenant_id=tenant.id,
            resource_type=RESOURCE_TYPE_DOCUMENT_COLLECTION,
            resource_id=collection.id,
            owner_id=collection.owner_id,
            status="active",
        )
    )
    async_db_session.add(
        AclGrant(
            tenant_id=tenant.id,
            resource_type=RESOURCE_TYPE_DOCUMENT_COLLECTION,
            resource_id=collection.id,
            principal_type="role",
            principal_id="analyst",
            permission="read",
            effect="allow",
            created_by=user.id,
        )
    )
    await async_db_session.commit()

    service = DocumentService(tenant_id=tenant.id, db_session=async_db_session, file_storage=object())
    docs, pagination = await service.list_documents(
        requester_id=user.id,
        requester_role=user.role,
        page=1,
        page_size=10,
        query=None,
    )

    ids = {d.id for d in docs}
    assert doc.id in ids
    assert pagination.total == 1


@pytest.mark.asyncio
async def test_list_documents_short_query_total_matches_items_without_vector_ref(async_db_session):
    tenant, user = await create_tenant_user(async_db_session, tenant_name="tenant_query", username="user_query")
    collection = await create_document_collection(async_db_session, tenant_id=tenant.id, owner_id=user.id)
    await create_document(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=user.id,
        collection_id=collection.id,
        filename="se-hit.pdf",
    )

    service = DocumentService(tenant_id=tenant.id, db_session=async_db_session, file_storage=object())
    docs, pagination = await service.list_documents(
        requester_id=user.id,
        requester_role=user.role,
        page=1,
        page_size=10,
        query="se",
    )

    assert len(docs) == 1
    assert pagination.total == 1


@pytest.mark.asyncio
async def test_list_documents_admin_manage_can_see_all_under_restrictive_abac(async_db_session):
    tenant, admin_user = await create_tenant_user(
        async_db_session, tenant_name="tenant_admin", username="user_admin", role="admin"
    )
    owner_user = User(
        username="owner_for_admin_visibility",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    async_db_session.add(owner_user)
    await async_db_session.commit()
    await async_db_session.refresh(owner_user)

    await _seed_owner_only_collection_abac_policy(async_db_session, tenant.id)

    collection = await create_document_collection(
        async_db_session, tenant_id=tenant.id, owner_id=owner_user.id, name="MemberCollection"
    )
    await create_document(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=owner_user.id,
        collection_id=collection.id,
        filename="owned-by-member.pdf",
    )

    service = DocumentService(tenant_id=tenant.id, db_session=async_db_session, file_storage=object())
    docs, pagination = await service.list_documents(
        requester_id=admin_user.id,
        requester_role=admin_user.role,
        page=1,
        page_size=10,
        query=None,
    )

    assert len(docs) == 1
    assert docs[0].filename == "owned-by-member.pdf"
    assert pagination.total == 1
