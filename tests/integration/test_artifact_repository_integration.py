"""Integration tests for ArtifactRepository."""

import pytest
import pytest_asyncio

from apps.shared.artifact.repository import ArtifactRepository
from apps.shared.db.models import Artifact, ArtifactLink, ChatThread

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
class TestArtifactRepository:
    """Test ArtifactRepository operations."""

    async def test_link_artifact(self, async_db_session, sample_thread_with_user):
        repo = ArtifactRepository(async_db_session)
        thread, tenant_id, user_id = sample_thread_with_user

        artifact = await repo.link_artifact(
            thread_id=thread.id,
            artifact_type="dashboard",
            resource_id=123,
            tenant_id=tenant_id,
            owner_id=user_id,
            title="Test Dashboard",
            url="/dashboards/123/embed",
            artifact_metadata={"dashboard_id": 123},
        )

        assert artifact.source_thread_id == thread.id
        assert artifact.artifact_type == "dashboard"
        assert artifact.resource_id == 123
        assert artifact.owner_id == user_id
        assert artifact.title == "Test Dashboard"
        assert artifact.url == "/dashboards/123/embed"
        assert artifact.artifact_metadata == {"dashboard_id": 123}
        assert artifact.id > 0

    async def test_link_artifact_idempotent(self, async_db_session, sample_thread_with_user):
        repo = ArtifactRepository(async_db_session)
        thread, tenant_id, user_id = sample_thread_with_user

        first = await repo.link_artifact(
            thread_id=thread.id,
            artifact_type="dashboard",
            resource_id=123,
            tenant_id=tenant_id,
            owner_id=user_id,
        )
        second = await repo.link_artifact(
            thread_id=thread.id,
            artifact_type="dashboard",
            resource_id=123,
            tenant_id=tenant_id,
            owner_id=user_id,
        )
        await async_db_session.commit()

        assert first.id == second.id
        count = await repo.count_linked_artifacts(thread.id)
        assert count == 1

    async def test_link_artifact_idempotent_backfills_missing_owner(self, async_db_session, sample_thread_with_user):
        """Backfill path fires when the in-memory artifact.owner_id is None.

        This exercises the ``if artifact.owner_id is None`` branch inside
        ``_get_or_create_artifact`` without needing to bypass the DB constraint.
        """
        from sqlalchemy.orm.attributes import set_committed_value

        repo = ArtifactRepository(async_db_session)
        thread, tenant_id, user_id = sample_thread_with_user

        first = await repo.link_artifact(
            thread_id=thread.id,
            artifact_type="dashboard",
            resource_id=456,
            tenant_id=tenant_id,
            owner_id=user_id,
        )
        await async_db_session.flush()

        # Zero-out owner_id in the identity map without marking it dirty.
        # set_committed_value bypasses SQLAlchemy's change tracking so no
        # UPDATE is emitted for owner_id=NULL before the repository's
        # backfill branch sets it back to user_id.
        set_committed_value(first, "owner_id", None)
        assert first.owner_id is None

        second = await repo.link_artifact(
            thread_id=thread.id,
            artifact_type="dashboard",
            resource_id=456,
            tenant_id=tenant_id,
            owner_id=user_id,
        )

        assert first.id == second.id
        assert second.owner_id == user_id

    async def test_list_linked_artifacts(self, async_db_session, sample_thread_with_user):
        repo = ArtifactRepository(async_db_session)
        thread, tenant_id, user_id = sample_thread_with_user

        await repo.link_artifact(
            thread_id=thread.id,
            artifact_type="dashboard",
            resource_id=1,
            tenant_id=tenant_id,
            owner_id=user_id,
            title="Dashboard 1",
        )
        await repo.link_artifact(
            thread_id=thread.id,
            artifact_type="chart",
            resource_id=2,
            tenant_id=tenant_id,
            owner_id=user_id,
            title="Chart 2",
        )
        await async_db_session.commit()

        artifacts = await repo.list_linked_artifacts(thread.id)

        assert len(artifacts) == 2
        assert artifacts[0].resource_id == 2
        assert artifacts[1].resource_id == 1

    async def test_list_linked_artifacts_with_type_filter(self, async_db_session, sample_thread_with_user):
        repo = ArtifactRepository(async_db_session)
        thread, tenant_id, user_id = sample_thread_with_user

        await repo.link_artifact(
            thread_id=thread.id,
            artifact_type="dashboard",
            resource_id=1,
            tenant_id=tenant_id,
            owner_id=user_id,
        )
        await repo.link_artifact(
            thread_id=thread.id,
            artifact_type="chart",
            resource_id=2,
            tenant_id=tenant_id,
            owner_id=user_id,
        )
        await repo.link_artifact(
            thread_id=thread.id,
            artifact_type="dashboard",
            resource_id=3,
            tenant_id=tenant_id,
            owner_id=user_id,
        )
        await async_db_session.commit()

        dashboards = await repo.list_linked_artifacts(thread.id, artifact_type="dashboard")
        charts = await repo.list_linked_artifacts(thread.id, artifact_type="chart")

        assert len(dashboards) == 2
        assert len(charts) == 1
        assert all(a.artifact_type == "dashboard" for a in dashboards)
        assert all(a.artifact_type == "chart" for a in charts)

    async def test_get_by_resource(self, async_db_session, sample_thread_with_user):
        repo = ArtifactRepository(async_db_session)
        thread, tenant_id, user_id = sample_thread_with_user

        await repo.link_artifact(
            thread_id=thread.id,
            artifact_type="dashboard",
            resource_id=123,
            tenant_id=tenant_id,
            owner_id=user_id,
            title="Test Dashboard",
        )
        await async_db_session.commit()

        artifact = await repo.get_by_resource(thread.id, "dashboard", 123)
        assert artifact is not None
        assert artifact.resource_id == 123
        assert artifact.title == "Test Dashboard"

        not_found = await repo.get_by_resource(thread.id, "dashboard", 999)
        assert not_found is None

    async def test_unlink_artifact(self, async_db_session, sample_thread_with_user):
        repo = ArtifactRepository(async_db_session)
        thread, tenant_id, user_id = sample_thread_with_user

        artifact = await repo.link_artifact(
            thread_id=thread.id,
            artifact_type="dashboard",
            resource_id=123,
            tenant_id=tenant_id,
            owner_id=user_id,
        )
        await async_db_session.commit()

        success = await repo.unlink_by_id(artifact.id, thread.id)
        await async_db_session.commit()
        assert success is True

        artifact_after = await repo.get_by_resource(thread.id, "dashboard", 123)
        assert artifact_after is None

    async def test_unlink_nonexistent_artifact(self, async_db_session, sample_thread_with_user):
        repo = ArtifactRepository(async_db_session)
        thread, _, _ = sample_thread_with_user

        success = await repo.unlink_artifact(thread.id, "dashboard", 999)
        assert success is False

    async def test_count_linked_artifacts(self, async_db_session, sample_thread_with_user):
        repo = ArtifactRepository(async_db_session)
        thread, tenant_id, user_id = sample_thread_with_user

        count = await repo.count_linked_artifacts(thread.id)
        assert count == 0

        await repo.link_artifact(
            thread_id=thread.id,
            artifact_type="dashboard",
            resource_id=1,
            tenant_id=tenant_id,
            owner_id=user_id,
        )
        await repo.link_artifact(
            thread_id=thread.id,
            artifact_type="chart",
            resource_id=2,
            tenant_id=tenant_id,
            owner_id=user_id,
        )
        await async_db_session.commit()

        count = await repo.count_linked_artifacts(thread.id)
        assert count == 2

    async def test_artifacts_survive_thread_deletion(self, async_db_session, sample_thread_with_user):
        repo = ArtifactRepository(async_db_session)
        thread, tenant_id, user_id = sample_thread_with_user

        await repo.link_artifact(
            thread_id=thread.id,
            artifact_type="dashboard",
            resource_id=123,
            tenant_id=tenant_id,
            owner_id=user_id,
        )
        await async_db_session.commit()

        count = await repo.count_linked_artifacts(thread.id)
        assert count == 1

        await async_db_session.delete(thread)
        await async_db_session.commit()

        from sqlalchemy import select

        result = await async_db_session.execute(
            select(Artifact).where(
                Artifact.artifact_type == "dashboard",
                Artifact.resource_id == 123,
                Artifact.tenant_id == tenant_id,
            )
        )
        artifacts = result.scalars().all()
        assert len(artifacts) == 1

        link_result = await async_db_session.execute(select(ArtifactLink).where(ArtifactLink.thread_id == thread.id))
        links = link_result.scalars().all()
        assert len(links) == 0


@pytest_asyncio.fixture
async def sample_thread_with_user(async_db_session):
    """Create a sample ChatThread with tenant and user for testing."""
    from apps.shared.db.models import Tenant, User

    tenant = Tenant(
        name="Test Tenant",
        slug="test-tenant",
        status="active",
    )
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(
        username="test_user",
        email="test@example.com",
        hashed_password="hashed_password",
        role="admin",
        tenant_id=tenant.id,
        status="active",
    )
    async_db_session.add(user)
    await async_db_session.flush()

    thread = ChatThread(
        id="test_thread_123",
        tenant_id=tenant.id,
        user_id=user.id,
        agent_id=1,
        title="Test Thread",
        message_count=0,
    )
    async_db_session.add(thread)
    await async_db_session.commit()
    await async_db_session.refresh(thread)
    return thread, tenant.id, user.id
