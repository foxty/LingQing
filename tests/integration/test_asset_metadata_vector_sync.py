"""Integration tests for asset metadata update and vector/FTS synchronization.

Tests that verify when asset metadata is updated:
1. ResourceIndex table is updated with new raw_content
2. Vector DB old chunks are deleted before adding new ones
3. FTS (PostgreSQL tsvector) is updated from tokenized_content
4. Both Vector DB and FTS stay synchronized after updates

Architecture tested:
  AssetMetadataService.update_asset_meta_override_for_actor()
    → ResourceIndexService.create_or_update()
    → ResourceIndex (stale status)
    → scheduler sync_all_pending()
    → Vector DB + FTS update
"""

from __future__ import annotations

import asyncio
import time

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.data_source.asset_metadata_service import AssetMetadataService
from apps.shared.data_source.domain import AssetMetadataDomain
from apps.shared.data_source.schemas import RAGSourceType
from apps.shared.db.models import AssetMetadata, DataSource, Tenant, User
from apps.shared.domain.actor import ActorContext
from apps.shared.tasks.domain import TaskExecutionContext
from apps.shared.domain.value_objects import AssetMetaVO, AssetType, ColumnVO, DataType
from apps.shared.infra.rag.rag_manager import RAGManager
from apps.shared.search.indexing_service import ResourceIndexService
from apps.shared.tasks.system.jobs.vector_sync import sync_to_vector_db
from tests.integration.tool_integration_helpers import SessionContext

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def patch_vector_sync_db(async_db_session, monkeypatch):
    monkeypatch.setattr(
        "apps.shared.tasks.system.jobs.vector_sync.app_db_session",
        lambda: SessionContext(async_db_session),
    )


@pytest_asyncio.fixture
async def test_tenant(async_db_session: AsyncSession):
    """Create a test tenant."""
    tenant = Tenant(name="test_tenant_vector_sync", slug="test-vector-sync")
    async_db_session.add(tenant)
    await async_db_session.flush()
    return tenant


@pytest_asyncio.fixture
async def test_user(async_db_session: AsyncSession, test_tenant: Tenant):
    """Create a test user."""
    user = User(
        username=f"test_user_{test_tenant.id}",
        email=f"test_{test_tenant.id}@example.com",
        hashed_password="hashed",
        role="admin",
        tenant_id=test_tenant.id,
        status="active",
    )
    async_db_session.add(user)
    await async_db_session.flush()
    return user


@pytest_asyncio.fixture
async def test_data_source(async_db_session: AsyncSession, test_tenant: Tenant, test_user: User):
    """Create a test managed data source."""
    url = async_db_session.bind.engine.url
    ds = DataSource(
        name="test_ds_vector_sync",
        type="managed_postgres",
        tenant_id=test_tenant.id,
        owner_id=test_user.id,
        config={
            "host": url.host,
            "port": url.port,
            "database": url.database,
            "user": url.username,
            "password": url.password,
        },
    )
    async_db_session.add(ds)
    await async_db_session.flush()
    return ds


@pytest_asyncio.fixture
async def test_asset(async_db_session: AsyncSession, test_data_source: DataSource, test_user: User):
    """Create a test asset with initial metadata."""
    columns = [
        ColumnVO(name="id", data_type=DataType.INTEGER),
        ColumnVO(name="name", data_type=DataType.TEXT),
        ColumnVO(name="value", data_type=DataType.FLOAT),
    ]

    meta = AssetMetaVO(
        description="Initial asset description for testing",
        column_description={"name": "Product name", "value": "Product price"},
    )

    asset_domain = AssetMetadataDomain.create_new(
        data_source_id=test_data_source.id,
        asset_name="test_products",
        asset_type=AssetType.TABLE,
        columns=columns,
        row_count=100,
        meta=meta,
        owner_id=test_user.id,
    )

    service = AssetMetadataService(tenant_id=test_data_source.tenant_id, db_session=async_db_session)
    asset = await service.create_asset(asset=asset_domain)
    await async_db_session.commit()

    return asset


@pytest_asyncio.fixture
async def actor_context(test_user: User, test_tenant: Tenant):
    """Create actor context for the test user."""
    return ActorContext(
        tenant_id=test_tenant.id,
        user_id=test_user.id,
        user_role="admin",
    )


@pytest_asyncio.fixture
async def rag_manager(test_tenant: Tenant):
    """Create RAG manager for vector operations."""
    return RAGManager(tenant_id=test_tenant.id)


async def _wait_until(condition_fn, timeout=10, interval=0.5):
    """Wait until condition is met or timeout."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            if await condition_fn():
                return True
        except Exception:
            pass
        await asyncio.sleep(interval)
    raise TimeoutError(f"Condition not met within {timeout}s")


class TestAssetMetadataUpdateVectorSync:
    """Test that asset metadata updates properly sync to both Vector DB and FTS."""

    async def test_update_asset_meta_updates_resource_index(
        self,
        async_db_session: AsyncSession,
        test_tenant: Tenant,
        test_asset: AssetMetadata,
        actor_context: ActorContext,
    ):
        """Verify that updating asset metadata creates/updates ResourceIndex record."""
        # Initial state: ResourceIndex should exist with initial content
        index_service = ResourceIndexService(tenant_id=test_tenant.id, db_session=async_db_session)
        initial_index = await index_service.get_by_resource(RAGSourceType.ASSET.value, test_asset.id)
        assert initial_index is not None
        assert initial_index.raw_content is not None

        initial_text = initial_index.raw_content.get("text", "")
        assert "Initial asset description" in initial_text

        # Update asset metadata
        service = AssetMetadataService(tenant_id=test_tenant.id, db_session=async_db_session)
        updated_asset = await service.update_asset_meta_override_for_actor(
            actor=actor_context,
            data_source_id=test_asset.data_source_id,
            asset_id=test_asset.id,
            description="Updated description for vector sync test",
            column_description={"name": "Updated product name field"},
        )

        # Verify ResourceIndex was updated with new content
        updated_index = await index_service.get_by_resource(RAGSourceType.ASSET.value, test_asset.id)
        assert updated_index is not None
        assert updated_index.raw_content is not None

        updated_text = updated_index.raw_content.get("text", "")
        assert "Updated description for vector sync test" in updated_text

        updated_asset_db = await async_db_session.get(AssetMetadata, test_asset.id)
        assert updated_asset_db is not None
        assert updated_asset_db.meta_override.get("column_description", {}).get("name") == (
            "Updated product name field"
        )

        # Status should be stale (needs re-indexing)
        assert updated_index.vector_status in ["stale", "pending"]

    async def test_sync_pending_deletes_old_vectors_before_adding_new(
        self,
        async_db_session: AsyncSession,
        test_tenant: Tenant,
        test_asset: AssetMetadata,
        actor_context: ActorContext,
        rag_manager: RAGManager,
    ):
        """Verify that sync deletes old vectors before adding new ones."""
        # Step 1: Create initial ResourceIndex and sync to vector DB
        index_service = ResourceIndexService(tenant_id=test_tenant.id, db_session=async_db_session)
        initial_index = await index_service.get_by_resource(RAGSourceType.ASSET.value, test_asset.id)

        # Manually trigger sync for initial content
        await async_db_session.commit()
        task_context: TaskExecutionContext = {"tenant_id": test_tenant.id}
        result = await sync_to_vector_db(task_context=task_context, mode="incremental")
        assert result.outcome == "success"

        # Get initial chunks from vector DB
        initial_chunks = await rag_manager.get_chunks_by_resource(
            resource_type=RAGSourceType.ASSET.value,
            resource_id=test_asset.id,
            limit=100,
        )
        initial_chunk_count = len(initial_chunks)
        assert initial_chunk_count > 0

        # Extract content from initial chunks
        initial_contents = [chunk.page_content for chunk in initial_chunks]
        assert any("initial asset description for testing" in content for content in initial_contents)

        # Step 2: Update asset metadata
        service = AssetMetadataService(tenant_id=test_tenant.id, db_session=async_db_session)
        await service.update_asset_meta_override_for_actor(
            actor=actor_context,
            data_source_id=test_asset.data_source_id,
            asset_id=test_asset.id,
            description="New updated description that should replace old content",
            column_description=None,
        )

        # Step 3: Sync again - this should delete old vectors and add new ones
        await async_db_session.commit()
        result = await sync_to_vector_db(task_context=task_context, mode="incremental")
        assert result.outcome == "success"

        # Step 4: Verify vector DB only has new content (no duplicates)
        await _wait_until(lambda: self._check_vector_count(rag_manager, test_asset.id, initial_chunk_count))

        final_chunks = await rag_manager.get_chunks_by_resource(
            resource_type=RAGSourceType.ASSET.value,
            resource_id=test_asset.id,
            limit=100,
        )

        # Should have similar number of chunks (not double)
        assert len(final_chunks) <= initial_chunk_count * 1.5, (
            f"Expected ~{initial_chunk_count} chunks, got {len(final_chunks)} - possible duplicate vectors"
        )

        # Should contain new content
        final_contents = [chunk.page_content for chunk in final_chunks]
        assert any("new updated description" in content for content in final_contents), (
            "New content not found in vector DB"
        )

        # Should NOT contain old content (or at least not predominantly)
        old_content_count = sum(
            1 for content in final_contents if "initial asset description for testing" in content
        )
        assert old_content_count == 0, (
            f"Found {old_content_count} chunks with old content - vectors not properly cleaned up"
        )

    async def _check_vector_count(self, rag_manager: RAGManager, resource_id: int, expected_max: int) -> bool:
        """Helper to check if vector count is within expected range."""
        chunks = await rag_manager.get_chunks_by_resource(
            resource_type=RAGSourceType.ASSET.value,
            resource_id=resource_id,
            limit=100,
        )
        return len(chunks) <= expected_max * 1.5

    async def test_fts_and_vector_stay_synchronized_after_update(
        self,
        async_db_session: AsyncSession,
        test_tenant: Tenant,
        test_asset: AssetMetadata,
        actor_context: ActorContext,
        rag_manager: RAGManager,
    ):
        """Verify that both FTS and Vector DB are updated and consistent."""
        index_service = ResourceIndexService(tenant_id=test_tenant.id, db_session=async_db_session)

        # Step 1: Initial sync
        task_context: TaskExecutionContext = {"tenant_id": test_tenant.id}
        await async_db_session.commit()
        await sync_to_vector_db(task_context=task_context, mode="incremental")

        # Verify initial state in both FTS and Vector DB
        initial_chunks = await rag_manager.get_chunks_by_resource(
            resource_type=RAGSourceType.ASSET.value,
            resource_id=test_asset.id,
            limit=100,
        )
        initial_fts_results = await index_service._repo.search_assets_fts(
            tenant_id=test_tenant.id,
            query="Initial asset description",
            limit=10,
        )

        assert len(initial_chunks) > 0, "No chunks in vector DB initially"
        assert len(initial_fts_results) > 0, "No FTS results initially"

        # Step 2: Update asset with completely different content
        service = AssetMetadataService(tenant_id=test_tenant.id, db_session=async_db_session)
        await service.update_asset_meta_override_for_actor(
            actor=actor_context,
            data_source_id=test_asset.data_source_id,
            asset_id=test_asset.id,
            description="Completely different content for synchronization test",
            column_description={"id": "Unique identifier", "name": "Item name", "value": "Numeric value"},
        )

        # Step 3: Sync to update both FTS and Vector DB
        await async_db_session.commit()
        await sync_to_vector_db(task_context=task_context, mode="incremental")

        # Step 4: Verify both are updated
        final_chunks = await rag_manager.get_chunks_by_resource(
            resource_type=RAGSourceType.ASSET.value,
            resource_id=test_asset.id,
            limit=100,
        )

        # Check Vector DB has new content
        final_vector_contents = [chunk.page_content for chunk in final_chunks]
        assert any("completely different content" in content for content in final_vector_contents), (
            "Vector DB not updated with new content"
        )

        # Check FTS has new content
        final_fts_results = await index_service._repo.search_assets_fts(
            tenant_id=test_tenant.id,
            query="Completely different content",
            limit=10,
        )
        assert len(final_fts_results) > 0, "FTS not updated with new content"

        # Verify old content is gone from both
        old_fts_results = await index_service._repo.search_assets_fts(
            tenant_id=test_tenant.id,
            query="Initial asset description",
            limit=10,
        )
        # Old content should not appear in top results (might still match partially)
        old_in_top = any(
            "Initial asset description" in (idx.raw_content or {}).get("text", "") for idx, _ in old_fts_results[:3]
        )
        assert not old_in_top, "Old content still prominent in FTS results"

    async def test_multiple_updates_dont_accumulate_duplicate_vectors(
        self,
        async_db_session: AsyncSession,
        test_tenant: Tenant,
        test_asset: AssetMetadata,
        actor_context: ActorContext,
        rag_manager: RAGManager,
    ):
        """Verify that multiple sequential updates don't accumulate duplicate vectors."""
        index_service = ResourceIndexService(tenant_id=test_tenant.id, db_session=async_db_session)
        task_context: TaskExecutionContext = {"tenant_id": test_tenant.id}

        # Initial sync
        await async_db_session.commit()
        await sync_to_vector_db(task_context=task_context, mode="incremental")

        initial_chunks = await rag_manager.get_chunks_by_resource(
            resource_type=RAGSourceType.ASSET.value,
            resource_id=test_asset.id,
            limit=100,
        )
        baseline_count = len(initial_chunks)

        # Perform multiple updates
        service = AssetMetadataService(tenant_id=test_tenant.id, db_session=async_db_session)
        for i in range(3):
            await service.update_asset_meta_override_for_actor(
                actor=actor_context,
                data_source_id=test_asset.data_source_id,
                asset_id=test_asset.id,
                description=f"Update iteration {i + 1} - testing duplicate prevention",
                column_description=None,
            )
            await async_db_session.commit()
            await sync_to_vector_db(task_context=task_context, mode="incremental")

        # Final check - should not have accumulated vectors
        final_chunks = await rag_manager.get_chunks_by_resource(
            resource_type=RAGSourceType.ASSET.value,
            resource_id=test_asset.id,
            limit=100,
        )

        # Allow some variance but shouldn't be more than 2x baseline
        assert len(final_chunks) <= baseline_count * 2, (
            f"Vectors accumulated: baseline={baseline_count}, final={len(final_chunks)}"
        )

        # Latest content should be present
        latest_contents = [chunk.page_content for chunk in final_chunks]
        assert any("update iteration 3" in content for content in latest_contents), (
            "Latest update not reflected in vector DB"
        )
