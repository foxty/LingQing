"""Unit tests for report service owner-only updates."""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from apps.shared.core.exceptions import AuthorizationError
from apps.shared.db.models import Artifact, ResourceAcl, Tenant, User
from apps.shared.domain.actor import ActorContext
from apps.shared.report.service import ReportService


@pytest.mark.asyncio
async def test_update_report_owner_can_update(async_db_session):
    tenant = Tenant(name="tenant_report_service", slug="tenant_report_service", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    owner = User(
        username="report_owner",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    async_db_session.add(owner)
    await async_db_session.flush()

    service = ReportService.create(tenant_id=tenant.id, db_session=async_db_session)

    created = await service.create_report(
        title="Initial report",
        content="Initial content",
        format="markdown",
        owner_id=owner.id,
        report_metadata={"length": len("Initial content")},
    )

    updated = await service.update_report_for_actor(
        report_id=created.report.id,
        actor=ActorContext(tenant_id=tenant.id, user_id=owner.id, user_role=owner.role),
        title="Updated report",
        content="Updated content",
        format="html",
        report_metadata={"length": len("Updated content")},
    )

    assert updated.id == created.report.id
    assert updated.title == "Updated report"
    assert updated.content == "Updated content"
    assert updated.format == "html"
    assert updated.report_metadata.get("length") == len("Updated content")


@pytest.mark.asyncio
async def test_update_report_non_owner_forbidden(async_db_session):
    tenant = Tenant(name="tenant_report_service_auth", slug="tenant_report_service_auth", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    owner = User(
        username="report_owner_auth",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    other_user = User(
        username="report_other_auth",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    async_db_session.add_all([owner, other_user])
    await async_db_session.flush()

    service = ReportService.create(tenant_id=tenant.id, db_session=async_db_session)

    created = await service.create_report(
        title="Owner report",
        content="Owner content",
        owner_id=owner.id,
    )

    with pytest.raises(AuthorizationError, match="Access denied"):
        await service.update_report_for_actor(
            report_id=created.report.id,
            actor=ActorContext(tenant_id=tenant.id, user_id=other_user.id, user_role=other_user.role),
            content="Illicit update",
        )


@pytest.mark.asyncio
async def test_update_report_owner_rejects_null_artifact_owner(async_db_session):
    tenant = Tenant(name="tenant_report_owner_fallback", slug="tenant_report_owner_fallback", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    owner = User(
        username="report_owner_fallback",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    async_db_session.add(owner)
    await async_db_session.flush()

    service = ReportService.create(tenant_id=tenant.id, db_session=async_db_session)
    created = await service.create_report(
        title="Fallback owner report",
        content="Initial",
        owner_id=owner.id,
    )

    artifact_stmt = select(Artifact).where(
        Artifact.tenant_id == tenant.id,
        Artifact.artifact_type == "report",
        Artifact.resource_id == created.report.id,
    )
    artifact = (await async_db_session.execute(artifact_stmt)).scalar_one()
    artifact.owner_id = None
    with pytest.raises(IntegrityError):
        await async_db_session.flush()


@pytest.mark.asyncio
async def test_require_owner_access_prefers_artifact_owner_over_created_by(async_db_session):
    tenant = Tenant(name="tenant_report_owner_precedence", slug="tenant_report_owner_precedence", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    creator = User(
        username="report_creator_precedence",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    assigned_owner = User(
        username="report_assigned_owner",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    async_db_session.add_all([creator, assigned_owner])
    await async_db_session.flush()

    service = ReportService.create(tenant_id=tenant.id, db_session=async_db_session)
    created = await service.create_report(
        title="Owner precedence report",
        content="Initial",
        owner_id=creator.id,
    )

    artifact_stmt = select(Artifact).where(
        Artifact.tenant_id == tenant.id,
        Artifact.artifact_type == "report",
        Artifact.resource_id == created.report.id,
    )
    artifact = (await async_db_session.execute(artifact_stmt)).scalar_one()
    artifact.owner_id = assigned_owner.id

    resource_acl_stmt = select(ResourceAcl).where(
        ResourceAcl.tenant_id == tenant.id,
        ResourceAcl.resource_type == "report",
        ResourceAcl.resource_id == created.report.id,
    )
    resource_acl = (await async_db_session.execute(resource_acl_stmt)).scalar_one()
    resource_acl.owner_id = assigned_owner.id
    await async_db_session.flush()

    with pytest.raises(AuthorizationError, match="Access denied"):
        await service.require_owner_access(
            report_id=created.report.id,
            actor=ActorContext(tenant_id=tenant.id, user_id=creator.id, user_role=creator.role),
        )

    await service.require_owner_access(
        report_id=created.report.id,
        actor=ActorContext(tenant_id=tenant.id, user_id=assigned_owner.id, user_role=assigned_owner.role),
    )
