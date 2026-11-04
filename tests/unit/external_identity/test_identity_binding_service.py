"""Unit tests for IdentityBindingService (in-memory SQLite)."""

from uuid import uuid4

import pytest

from apps.shared.external_identity.domain import (
    POLICY_PENDING,
    BindAction,
    ExtractedIdentity,
    STATUS_ACTIVE,
    STATUS_PENDING,
)
from apps.shared.external_identity.repository import ExternalIdentityRepository
from apps.shared.external_identity.service import IdentityBindingService
from apps.shared.external_identity.identity_source_repository import IdentitySourceRepository

pytestmark = pytest.mark.asyncio


async def _tenant_and_source(db):
    from apps.shared.db.models import Tenant

    tenant = Tenant(name=f"T-{uuid4().hex[:6]}", slug=f"t-{uuid4().hex[:6]}", status="active")
    db.add(tenant)
    await db.flush()
    await db.refresh(tenant)
    source_repo = IdentitySourceRepository(db)
    source = await source_repo.create_login_provider_source(
        tenant_id=tenant.id,
        display_name="Google",
        bind_policy=POLICY_PENDING,
    )
    return tenant, source


async def _member(db, tenant_id: int, email: str):
    from apps.shared.db.models import TenantMembership, User

    user = User(
        username=f"u-{uuid4().hex[:6]}",
        email=email.lower(),
        hashed_password="x",
        role="member",
        tenant_id=tenant_id,
        status="active",
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    db.add(
        TenantMembership(
            tenant_id=tenant_id,
            user_id=user.id,
            status="active",
            is_break_glass=False,
        )
    )
    await db.flush()
    return user


async def test_second_sso_callback_reuses_pending_row(async_db_session):
    """Repeat OAuth with an existing pending subject must not INSERT again."""
    tenant, source = await _tenant_and_source(async_db_session)
    repo = ExternalIdentityRepository(async_db_session)
    subject = f"google-sub-{uuid4().hex[:8]}"
    email = f"user-{uuid4().hex[:6]}@company.com"
    pending = await repo.create_identity(
        tenant_id=tenant.id,
        identity_source_id=source.id,
        external_subject=subject,
        user_id=None,
        email=email,
        display_name="User",
        status=STATUS_PENDING,
    )
    service = IdentityBindingService(async_db_session)
    result = await service.resolve_or_bind(
        tenant_id=tenant.id,
        identity_source_id=source.id,
        extracted=ExtractedIdentity(external_subject=subject, email=email, display_name="User"),
        allowed_domains=["company.com"],
        policy=POLICY_PENDING,
    )
    assert result.action == BindAction.PENDING
    assert result.identity_id == pending.id
    assert result.reason == "subject_pending"


async def test_pending_subject_attaches_after_admin_adds_user(async_db_session):
    """OAuth first (pending) then admin adds user -> second OAuth attaches and logs in."""
    tenant, source = await _tenant_and_source(async_db_session)
    repo = ExternalIdentityRepository(async_db_session)
    subject = f"google-sub-{uuid4().hex[:8]}"
    email = f"lynx-{uuid4().hex[:6]}@company.com"
    pending = await repo.create_identity(
        tenant_id=tenant.id,
        identity_source_id=source.id,
        external_subject=subject,
        user_id=None,
        email=email,
        display_name="Lynx",
        status=STATUS_PENDING,
    )
    member = await _member(async_db_session, tenant.id, email)
    service = IdentityBindingService(async_db_session)
    result = await service.resolve_or_bind(
        tenant_id=tenant.id,
        identity_source_id=source.id,
        extracted=ExtractedIdentity(external_subject=subject, email=email, display_name="Lynx"),
        allowed_domains=["company.com"],
        policy=POLICY_PENDING,
    )
    assert result.action == BindAction.ATTACH
    assert result.user_id == member.id
    assert result.identity_id == pending.id
    row = await repo.get_identity_by_subject(tenant.id, source.id, subject)
    assert row is not None
    assert row.status == STATUS_ACTIVE
    assert row.user_id == member.id
