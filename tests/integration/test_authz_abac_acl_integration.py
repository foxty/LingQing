"""Integration tests for ABAC simulation and ACL list filtering."""

import pytest
from sqlalchemy import select

from apps.shared.api_connector.domain import RatePolicyDomain
from apps.shared.api_connector.service import ApiConnectorService
from apps.shared.authz.authz_query_builder import evaluate_resource_action
from apps.shared.authz.service import AbacPolicyService
from apps.shared.core.exceptions import AuthorizationError
from apps.shared.data_source.asset_metadata_service import AssetMetadataService
from apps.shared.data_source.repository import AssetMetadataRepository, DataSourceRepository
from apps.shared.data_source.service import DataSourceService
from apps.shared.db.models import (
    AbacPolicy,
    AclGrant,
    ApiConnector,
    AssetMetadata,
    DataSource,
    Document,
    DocumentCollection,
    ResourceAcl,
    Tenant,
    User,
)
from apps.shared.domain.actor import ActorContext


@pytest.mark.asyncio
async def test_abac_simulation_resolves_api_connector_owner(async_db_session):
    tenant = Tenant(name="tenant_authz_it_abac", slug="tenant_authz_it_abac", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    owner = User(username="abac_owner", email=None, hashed_password="hashed", role="admin", tenant_id=tenant.id)
    other = User(username="abac_other", email=None, hashed_password="hashed", role="member", tenant_id=tenant.id)
    async_db_session.add_all([owner, other])
    await async_db_session.flush()

    connector = ApiConnector(
        tenant_id=tenant.id,
        owner_id=owner.id,
        name="abac-owner-connector",
        description=None,
        base_url="https://example.com",
        auth_type="none",
        auth_config={},
        rate_policy={},
        schema_source_type="openapi_upload",
        schema_source_url=None,
        status="active",
    )
    async_db_session.add(connector)
    await async_db_session.flush()

    service = AbacPolicyService.create(tenant.id, async_db_session)
    expression = ":user.id equals :resource.owner_id"

    allowed_owner, _ = await service.simulate_policy(
        expression=expression,
        resource_type="api_connector",
        action="read",
        user_id=owner.id,
        user_role=owner.role,
        resource_id=connector.id,
    )
    assert allowed_owner is True

    allowed_other, _ = await service.simulate_policy(
        expression=expression,
        resource_type="api_connector",
        action="read",
        user_id=other.id,
        user_role=other.role,
        resource_id=connector.id,
    )
    assert allowed_other is False


@pytest.mark.asyncio
async def test_acl_deny_does_not_block_abac_visible_connector_in_list(async_db_session):
    tenant = Tenant(name="tenant_authz_it_acl", slug="tenant_authz_it_acl", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    admin = User(username="acl_admin", email=None, hashed_password="hashed", role="admin", tenant_id=tenant.id)
    viewer = User(username="acl_viewer", email=None, hashed_password="hashed", role="viewer", tenant_id=tenant.id)
    async_db_session.add_all([admin, viewer])
    await async_db_session.flush()

    service = ApiConnectorService(tenant_id=tenant.id, db_session=async_db_session)

    blocked = await service.create_connector(
        owner_id=admin.id,
        name="blocked-by-acl",
        description=None,
        base_url="https://api.blocked.local",
        auth_type="none",
        auth_config={},
        rate_policy=RatePolicyDomain.from_raw({}),
        schema_source_type="openapi_upload",
        schema_source_url=None,
    )
    visible = await service.create_connector(
        owner_id=admin.id,
        name="visible-no-acl",
        description=None,
        base_url="https://api.visible.local",
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
            resource_id=blocked.id,
            owner_id=blocked.owner_id,
            status="active",
        )
    )
    async_db_session.add(
        AclGrant(
            tenant_id=tenant.id,
            resource_type="api_connector",
            resource_id=blocked.id,
            principal_type="user",
            principal_id=str(viewer.id),
            permission="read",
            effect="deny",
            created_by=admin.id,
        )
    )
    await async_db_session.flush()

    rows = await service.list_connectors_for_actor(
        actor=ActorContext(tenant_id=tenant.id, user_id=viewer.id, user_role=viewer.role)
    )

    listed_ids = {row.id for row in rows}
    assert blocked.id in listed_ids
    assert visible.id in listed_ids


@pytest.mark.asyncio
async def test_acl_allow_includes_connector_in_list(async_db_session):
    tenant = Tenant(name="tenant_authz_it_acl_allow", slug="tenant_authz_it_acl_allow", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    admin = User(username="acl_admin_allow", email=None, hashed_password="hashed", role="admin", tenant_id=tenant.id)
    viewer = User(username="acl_viewer_allow", email=None, hashed_password="hashed", role="viewer", tenant_id=tenant.id)
    async_db_session.add_all([admin, viewer])
    await async_db_session.flush()

    service = ApiConnectorService(tenant_id=tenant.id, db_session=async_db_session)
    connector = await service.create_connector(
        owner_id=admin.id,
        name="allowed-by-acl",
        description=None,
        base_url="https://api.allowed.local",
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

    rows = await service.list_connectors_for_actor(
        actor=ActorContext(tenant_id=tenant.id, user_id=viewer.id, user_role=viewer.role)
    )
    listed_ids = {row.id for row in rows}
    assert connector.id in listed_ids


@pytest.mark.asyncio
async def test_acl_inactive_does_not_block_abac_visible_connector_in_list(async_db_session):
    tenant = Tenant(name="tenant_authz_it_acl_inactive", slug="tenant_authz_it_acl_inactive", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    admin = User(
        username="acl_admin_inactive",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    viewer = User(
        username="acl_viewer_inactive",
        email=None,
        hashed_password="hashed",
        role="viewer",
        tenant_id=tenant.id,
    )
    async_db_session.add_all([admin, viewer])
    await async_db_session.flush()

    service = ApiConnectorService(tenant_id=tenant.id, db_session=async_db_session)
    connector = await service.create_connector(
        owner_id=admin.id,
        name="inactive-acl-connector",
        description=None,
        base_url="https://api.inactive.local",
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
            status="inactive",
        )
    )
    await async_db_session.flush()

    rows = await service.list_connectors_for_actor(
        actor=ActorContext(tenant_id=tenant.id, user_id=viewer.id, user_role=viewer.role)
    )
    listed_ids = {row.id for row in rows}
    assert connector.id in listed_ids


@pytest.mark.asyncio
async def test_get_connector_for_actor_acl_deny_does_not_block_abac_visible(async_db_session):
    tenant = Tenant(name="tenant_authz_it_get_deny", slug="tenant_authz_it_get_deny", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    admin = User(username="get_deny_admin", email=None, hashed_password="hashed", role="admin", tenant_id=tenant.id)
    viewer = User(username="get_deny_viewer", email=None, hashed_password="hashed", role="viewer", tenant_id=tenant.id)
    async_db_session.add_all([admin, viewer])
    await async_db_session.flush()

    service = ApiConnectorService(tenant_id=tenant.id, db_session=async_db_session)
    connector = await service.create_connector(
        owner_id=admin.id,
        name="get-denied-by-acl",
        description=None,
        base_url="https://api.get-deny.local",
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
            effect="deny",
            created_by=admin.id,
        )
    )
    await async_db_session.flush()

    got = await service.get_connector_for_actor(
        connector_id=connector.id,
        actor=ActorContext(tenant_id=tenant.id, user_id=viewer.id, user_role=viewer.role),
    )

    assert got.id == connector.id


@pytest.mark.asyncio
async def test_get_connector_for_actor_acl_inactive_does_not_block_abac_visible(async_db_session):
    tenant = Tenant(name="tenant_authz_it_get_inactive", slug="tenant_authz_it_get_inactive", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    admin = User(
        username="get_inactive_admin",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    viewer = User(
        username="get_inactive_viewer",
        email=None,
        hashed_password="hashed",
        role="viewer",
        tenant_id=tenant.id,
    )
    async_db_session.add_all([admin, viewer])
    await async_db_session.flush()

    service = ApiConnectorService(tenant_id=tenant.id, db_session=async_db_session)
    connector = await service.create_connector(
        owner_id=admin.id,
        name="get-inactive-acl",
        description=None,
        base_url="https://api.get-inactive.local",
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
            status="inactive",
        )
    )
    await async_db_session.flush()

    got = await service.get_connector_for_actor(
        connector_id=connector.id,
        actor=ActorContext(tenant_id=tenant.id, user_id=viewer.id, user_role=viewer.role),
    )

    assert got.id == connector.id


@pytest.mark.asyncio
async def test_get_connector_for_actor_acl_allow_overrides_abac_deny(async_db_session):
    tenant = Tenant(name="tenant_authz_it_get_abac_deny", slug="tenant_authz_it_get_abac_deny", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    admin = User(username="get_abac_admin", email=None, hashed_password="hashed", role="admin", tenant_id=tenant.id)
    viewer = User(username="get_abac_viewer", email=None, hashed_password="hashed", role="viewer", tenant_id=tenant.id)
    async_db_session.add_all([admin, viewer])
    await async_db_session.flush()

    service = ApiConnectorService(tenant_id=tenant.id, db_session=async_db_session)
    connector = await service.create_connector(
        owner_id=admin.id,
        name="get-abac-denied",
        description=None,
        base_url="https://api.get-abac-denied.local",
        auth_type="none",
        auth_config={},
        rate_policy=RatePolicyDomain.from_raw({}),
        schema_source_type="openapi_upload",
        schema_source_url=None,
    )

    async_db_session.add(
        AbacPolicy(
            tenant_id=tenant.id,
            name="require_sales_tag_for_read",
            description=None,
            resource_type="api_connector",
            action="read",
            expression=':user.tags has "dept:sales"',
            status="active",
            created_by=admin.id,
            updated_by=admin.id,
        )
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

    got = await service.get_connector_for_actor(
        connector_id=connector.id,
        actor=ActorContext(tenant_id=tenant.id, user_id=viewer.id, user_role=viewer.role),
    )

    assert got.id == connector.id


@pytest.mark.asyncio
async def test_update_connector_for_actor_acl_write_allow_succeeds(async_db_session):
    tenant = Tenant(name="tenant_authz_it_update_allow", slug="tenant_authz_it_update_allow", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    admin = User(
        username="update_allow_admin",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    editor = User(
        username="update_allow_editor",
        email=None,
        hashed_password="hashed",
        role="editor",
        tenant_id=tenant.id,
    )
    async_db_session.add_all([admin, editor])
    await async_db_session.flush()

    service = ApiConnectorService(tenant_id=tenant.id, db_session=async_db_session)
    connector = await service.create_connector(
        owner_id=admin.id,
        name="write-allowed",
        description="before",
        base_url="https://api.write-allowed.local",
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
            principal_id=str(editor.id),
            permission="write",
            effect="allow",
            created_by=admin.id,
        )
    )
    await async_db_session.flush()

    updated = await service.update_connector_for_actor(
        connector_id=connector.id,
        actor=ActorContext(tenant_id=tenant.id, user_id=editor.id, user_role=editor.role),
        description="after",
    )

    assert updated.description == "after"


@pytest.mark.asyncio
async def test_update_connector_for_actor_acl_write_deny_does_not_block_abac_visible(async_db_session):
    tenant = Tenant(name="tenant_authz_it_update_deny", slug="tenant_authz_it_update_deny", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    admin = User(
        username="update_deny_admin",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    editor = User(
        username="update_deny_editor",
        email=None,
        hashed_password="hashed",
        role="editor",
        tenant_id=tenant.id,
    )
    async_db_session.add_all([admin, editor])
    await async_db_session.flush()

    service = ApiConnectorService(tenant_id=tenant.id, db_session=async_db_session)
    connector = await service.create_connector(
        owner_id=admin.id,
        name="write-denied",
        description="before",
        base_url="https://api.write-denied.local",
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
            principal_id=str(editor.id),
            permission="write",
            effect="deny",
            created_by=admin.id,
        )
    )
    await async_db_session.flush()

    updated = await service.update_connector_for_actor(
        connector_id=connector.id,
        actor=ActorContext(tenant_id=tenant.id, user_id=editor.id, user_role=editor.role),
        description="after",
    )

    assert updated.description == "after"


@pytest.mark.asyncio
async def test_document_collection_single_resource_abac_owner_policy(async_db_session):
    tenant = Tenant(name="tenant_authz_it_doc_owner", slug="tenant_authz_it_doc_owner", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    owner = User(username="doc_owner", email=None, hashed_password="hashed", role="member", tenant_id=tenant.id)
    other = User(username="doc_other", email=None, hashed_password="hashed", role="member", tenant_id=tenant.id)
    async_db_session.add_all([owner, other])
    await async_db_session.flush()

    collection = DocumentCollection(
        tenant_id=tenant.id,
        name="OwnerCollection",
        owner_id=owner.id,
    )
    async_db_session.add(collection)
    await async_db_session.flush()

    doc = Document(
        tenant_id=tenant.id,
        collection_id=collection.id,
        filename="owner-policy.pdf",
        file_url="file://owner-policy",
        file_size=128,
        file_hash="hash",
        owner_id=owner.id,
        status="active",
    )
    async_db_session.add(doc)

    async_db_session.add(
        AbacPolicy(
            tenant_id=tenant.id,
            name="collection_owner_read_only",
            description=None,
            resource_type="document_collection",
            action="read",
            expression=":user.id equals :resource.owner_id",
            status="active",
            created_by=owner.id,
            updated_by=owner.id,
        )
    )
    await async_db_session.flush()

    allowed_owner = await evaluate_resource_action(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=owner.id,
        user_role=owner.role,
        resource_type="document_collection",
        resource_id=collection.id,
        resource_owner_id=collection.owner_id,
        action="read",
    )
    allowed_other = await evaluate_resource_action(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=other.id,
        user_role=other.role,
        resource_type="document_collection",
        resource_id=collection.id,
        resource_owner_id=collection.owner_id,
        action="read",
    )

    assert allowed_owner is True
    assert allowed_other is False


@pytest.mark.asyncio
async def test_data_source_acl_share_grants_asset_access_via_container(async_db_session):
    tenant = Tenant(name="tenant_authz_it_ds_acl", slug="tenant_authz_it_ds_acl", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    owner = User(username="ds_owner", email=None, hashed_password="hashed", role="admin", tenant_id=tenant.id)
    viewer = User(username="ds_viewer", email=None, hashed_password="hashed", role="member", tenant_id=tenant.id)
    async_db_session.add_all([owner, viewer])
    await async_db_session.flush()

    data_source = DataSource(
        tenant_id=tenant.id,
        name="shared_ds",
        type="sqlite",
        managed=True,
        config={},
        owner_id=owner.id,
    )
    async_db_session.add(data_source)
    await async_db_session.flush()

    async_db_session.add(
        AbacPolicy(
            tenant_id=tenant.id,
            name="data_source_owner_read",
            description=None,
            resource_type="data_source",
            action="read",
            expression=':user.role equals "admin" or :user.id equals :resource.owner_id',
            status="active",
            created_by=owner.id,
            updated_by=owner.id,
        )
    )

    async_db_session.add(
        ResourceAcl(
            tenant_id=tenant.id,
            resource_type="data_source",
            resource_id=data_source.id,
            owner_id=owner.id,
            status="active",
        )
    )
    async_db_session.add(
        AclGrant(
            tenant_id=tenant.id,
            resource_type="data_source",
            resource_id=data_source.id,
            principal_type="user",
            principal_id=str(viewer.id),
            permission="read",
            effect="allow",
            created_by=owner.id,
        )
    )
    await async_db_session.flush()

    shared_asset = AssetMetadata(
        data_source_id=data_source.id,
        asset_name="shared_orders",
        asset_type="table",
        columns=[],
        source_info={},
        owner_id=owner.id,
    )
    private_ds = DataSource(
        tenant_id=tenant.id,
        name="private_ds",
        type="sqlite",
        managed=True,
        config={},
        owner_id=owner.id,
    )
    async_db_session.add_all([shared_asset, private_ds])
    await async_db_session.flush()

    private_asset = AssetMetadata(
        data_source_id=private_ds.id,
        asset_name="private_orders",
        asset_type="table",
        columns=[],
        source_info={},
        owner_id=owner.id,
    )
    async_db_session.add(private_asset)
    await async_db_session.flush()

    allowed = await evaluate_resource_action(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=viewer.id,
        user_role=viewer.role,
        resource_type="data_source",
        resource_id=data_source.id,
        resource_owner_id=data_source.owner_id,
        action="read",
    )

    assert allowed is True

    asset_service = AssetMetadataService(tenant_id=tenant.id, db_session=async_db_session)
    viewer_actor = ActorContext(tenant_id=tenant.id, user_id=viewer.id, user_role=viewer.role)

    shared_assets, shared_pagination = await asset_service.list_assets_for_actor(
        actor=viewer_actor,
        data_source_id=data_source.id,
    )
    assert shared_pagination.total == 1
    assert shared_assets[0].asset_name == "shared_orders"

    with pytest.raises(AuthorizationError):
        await asset_service.list_assets_for_actor(
            actor=viewer_actor,
            data_source_id=private_ds.id,
        )

    ds_service = DataSourceService(
        tenant_id=tenant.id,
        data_source_repo=DataSourceRepository(async_db_session),
        asset_repo=AssetMetadataRepository(async_db_session),
    )
    scope = await ds_service.build_asset_access_scope(actor=viewer_actor, action="read")
    stmt = select(AssetMetadata.id).where(scope.asset_filter)
    visible_asset_ids = set((await async_db_session.execute(stmt)).scalars().all())
    assert visible_asset_ids == {shared_asset.id}
    assert private_asset.id not in visible_asset_ids
