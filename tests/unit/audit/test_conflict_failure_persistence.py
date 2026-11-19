"""Conflict-rejection audit rows must survive request-session rollback."""

from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.shared.core.exceptions import DuplicateResourceError
from apps.shared.db.models import AuditEvent, Base, Tenant, TenantMembership, User
from apps.tenant_app_service.auth.domain import MembershipStatus, UserRole
from apps.tenant_app_service.tenant.user_management_service import TenantUserManagementService

_SHARED_SQLITE = "sqlite+aiosqlite:///file:conflictfail?mode=memory&cache=shared&uri=true"


@pytest.mark.asyncio
async def test_user_create_duplicate_failure_audit_survives_request_rollback(monkeypatch):
    """Simulates get_db rollback after DuplicateResourceError; failure row must remain."""
    engine = create_async_engine(_SHARED_SQLITE, connect_args={"uri": True})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    request_session = session_factory()

    try:
        tenant = Tenant(name="audit-conflict", slug="audit-conflict", status="active")
        request_session.add(tenant)
        await request_session.flush()
        tenant_id = tenant.id

        admin = User(
            username="admin_cf",
            hashed_password="x",
            role=UserRole.ADMIN,
            tenant_id=tenant_id,
            status="active",
        )
        dup = User(
            username="taken",
            hashed_password="x",
            role=UserRole.MEMBER,
            tenant_id=tenant_id,
            status="active",
        )
        request_session.add_all([admin, dup])
        await request_session.flush()
        admin_id = admin.id
        request_session.add_all(
            [
                TenantMembership(tenant_id=tenant_id, user_id=admin_id, status=MembershipStatus.ACTIVE),
                TenantMembership(tenant_id=tenant_id, user_id=dup.id, status=MembershipStatus.ACTIVE),
            ]
        )
        await request_session.commit()

        @asynccontextmanager
        async def _committed_side_session():
            session = session_factory()
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

        monkeypatch.setattr(
            "apps.shared.audit_event.record_helpers.app_db_session",
            _committed_side_session,
        )

        service = TenantUserManagementService(tenant_id=tenant_id, db=request_session)
        with pytest.raises(DuplicateResourceError):
            await service.create_user(
                username="taken",
                password="pw",
                role=UserRole.MEMBER,
                actor_user_id=admin_id,
            )

        await request_session.rollback()

        async with session_factory() as verify:
            result = await verify.execute(
                select(AuditEvent.event_type, AuditEvent.outcome).where(AuditEvent.tenant_id == tenant_id)
            )
            rows = result.all()

        assert ("user.create", "failure") in rows, (
            f"expected failure audit after rollback; OUTCOMES: {[r[1] for r in rows]}"
        )
    finally:
        await request_session.close()
        await engine.dispose()