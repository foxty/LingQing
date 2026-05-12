"""E2E integration tests for vector_sync.py orchestration layer.

Tests the complete flow:
1. Resource creation → ResourceIndex record (pending status)
2. sync_to_vector_db() → Vector DB indexing
3. Resource deletion → Vector cleanup
4. Orphan detection and cleanup

Architecture tested:
  API/Service → ResourceIndex (pending) → vector_sync.sync_to_vector_db() → Vector DB
"""

from __future__ import annotations

import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import pytest_asyncio
from langchain_core.embeddings import Embeddings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from apps.shared.core.auth import get_current_user
from apps.shared.data_source.schemas import RAGSourceType
from apps.shared.db.models import DataSource, Document, DocumentCollection, Tenant, User
from apps.shared.db.session import get_db
from apps.shared.tasks.domain import TaskExecutionContext
from apps.shared.infra.rag.chroma_backend import get_vector_backend as build_vector_backend
from apps.shared.infra.rag.rag_manager import RAGManager
from apps.shared.infra.storage.file_storage import LocalFileStorage
from apps.shared.schemas.user import UserDTO
from apps.shared.search.domain import VectorStatus
from apps.shared.search.indexing_service import ResourceIndexService
from apps.shared.search.search_service import SearchService
from apps.shared.tasks.system.jobs.document_parse import run_document_parse_jobs
from apps.shared.tasks.system.jobs.vector_sync import cleanup_orphaned_vectors, sync_to_vector_db
from apps.tenant_app_service.routers.documents import get_file_storage_dependency
from apps.tenant_app_service.server import app

pytestmark = pytest.mark.asyncio


class KeywordEmbeddings(Embeddings):
    """Deterministic embeddings for Chroma integration tests."""

    _keywords = [
        "alpha",
        "beta",
        "document",
        "asset",
        "operation",
        "orders",
        "shared",
    ]

    def _encode(self, text: str) -> list[float]:
        lowered = text.lower()
        return [float(lowered.count(keyword)) for keyword in self._keywords]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._encode(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._encode(text)


async def _wait_until(assertion_coro, timeout_seconds: float = 8.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error = None
    while time.monotonic() < deadline:
        try:
            await assertion_coro()
            return
        except AssertionError as exc:
            last_error = exc
            await asyncio.sleep(0.2)

    if last_error is not None:
        raise last_error
    raise AssertionError("Condition was not met before timeout")


async def _parse_pending_documents(task_context: TaskExecutionContext) -> None:
    result = await run_document_parse_jobs(task_context=task_context)
    assert result.outcome == "success", getattr(result, "message", result)
    details = result.data.get("details", {})
    assert details.get("completed", 0) >= 1


@pytest_asyncio.fixture
async def vector_sync_e2e_env(async_db_session: AsyncSession, tmp_path: Path, monkeypatch, chroma_http_endpoint):
    """Setup environment for vector_sync e2e tests.

    Creates:
    - Tenant + User for auth context
    - DataSource for assets
    - Test file storage
    - ChromaDB connection
    - RAGManager for vector verification
    """
    host, port = chroma_http_endpoint
    prefix = f"it_e2e_{uuid.uuid4().hex}_tenant_"
    embeddings = KeywordEmbeddings()

    monkeypatch.setattr("apps.config.EnvConfig.DATA_ROOT_PATH", str(tmp_path))
    monkeypatch.setattr("apps.config.EnvConfig.FILE_STORAGE_TYPE", "local")
    monkeypatch.setattr("apps.config.EnvConfig.DOCUMENT_PARSER", "default")
    monkeypatch.setattr("apps.config.EnvConfig.DOCLING_SERVICE_URL", "")
    monkeypatch.setattr("apps.config.EnvConfig.MINERU_SERVICE_URL", "")
    chroma_url = f"http://{host}:{port}"
    monkeypatch.setattr("apps.config.EnvConfig.CHROMA_MODE", "http")
    monkeypatch.setattr("apps.config.EnvConfig.CHROMA_URL", chroma_url)
    monkeypatch.setattr("apps.config.EnvConfig.CHROMA_COLLECTION_PREFIX", prefix)
    monkeypatch.setattr("apps.shared.infra.rag.chroma_backend.EnvConfig.CHROMA_MODE", "http")
    monkeypatch.setattr("apps.shared.infra.rag.chroma_backend.EnvConfig.CHROMA_URL", chroma_url)
    monkeypatch.setattr("apps.shared.infra.rag.chroma_backend.EnvConfig.CHROMA_COLLECTION_PREFIX", prefix)

    def _test_vector_backend(tenant_id: int, embeddings: Embeddings | None = None):
        return build_vector_backend(tenant_id=tenant_id, embeddings=embeddings or vector_sync_e2e_env_embeddings)

    vector_sync_e2e_env_embeddings = embeddings
    monkeypatch.setattr("apps.shared.infra.rag.rag_manager.get_vector_backend", _test_vector_backend)

    session_url = async_db_session.bind.engine.url.render_as_string(hide_password=False)
    test_engine = create_async_engine(session_url, future=True, poolclass=NullPool)
    test_session_factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    @asynccontextmanager
    async def _test_app_db_session():
        async with test_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    monkeypatch.setattr("apps.shared.tasks.system.jobs.vector_sync.app_db_session", _test_app_db_session)
    monkeypatch.setattr("apps.shared.tasks.system.jobs.document_parse.app_db_session", _test_app_db_session)

    async def override_get_db():
        async with test_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    suffix = uuid.uuid4().hex[:8]
    async with test_session_factory() as seed_session:
        tenant = Tenant(name=f"vector-sync-e2e-{suffix}", slug=f"vector-sync-e2e-{suffix}", status="active")
        seed_session.add(tenant)
        await seed_session.flush()

        user = User(
            username=f"vector_sync_admin_{suffix}",
            email=f"vector_sync_{suffix}@test.local",
            hashed_password="hashed",
            role="admin",
            tenant_id=tenant.id,
            status="active",
        )
        seed_session.add(user)
        await seed_session.flush()

        url = seed_session.bind.engine.url
        data_source = DataSource(
            tenant_id=tenant.id,
            name=f"vector_sync_ds_{suffix}",
            type="postgres",
            managed=True,
            config={
                "host": url.host,
                "port": url.port,
                "database": url.database,
                "username": url.username,
                "password": url.password,
            },
            owner_id=user.id,
        )
        seed_session.add(data_source)
        collection = DocumentCollection(
            tenant_id=tenant.id,
            name="General",
            owner_id=user.id,
            description="Default test collection",
        )
        seed_session.add(collection)
        await seed_session.flush()
        await seed_session.commit()

    current_user = UserDTO(
        id=user.id,
        username=user.username,
        role=user.role,
        tenant_id=tenant.id,
        tenant_name=tenant.name,
    )

    async def override_user():
        return current_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_file_storage_dependency] = lambda: LocalFileStorage()

    task_context: TaskExecutionContext = {"tenant_id": tenant.id}

    yield {
        "session_factory": test_session_factory,
        "tenant_id": tenant.id,
        "user_id": user.id,
        "data_source_id": data_source.id,
        "collection_id": collection.id,
        "embeddings": embeddings,
        "task_context": task_context,
        "file_storage": LocalFileStorage(),
    }

    app.dependency_overrides.clear()
    await test_engine.dispose()


async def test_document_sync_to_vector_db_e2e(vector_sync_e2e_env):
    """Test document upload → ResourceIndex (pending) → sync_to_vector_db → Vector DB.

    Flow:
    1. Upload document via API → creates Document + ResourceIndex (pending)
    2. Call sync_to_vector_db() → indexes to ChromaDB
    3. Verify vector presence via RAGManager
    4. Delete document → ResourceIndex deleted
    5. Call sync_to_vector_db() again → vector removed
    """
    from fastapi.testclient import TestClient

    session_factory = vector_sync_e2e_env["session_factory"]
    tenant_id = vector_sync_e2e_env["tenant_id"]
    collection_id = vector_sync_e2e_env["collection_id"]
    task_context = vector_sync_e2e_env["task_context"]
    embeddings = vector_sync_e2e_env["embeddings"]
    file_storage = vector_sync_e2e_env["file_storage"]

    manager = RAGManager(tenant_id=tenant_id, embeddings=embeddings)

    with TestClient(app) as client:
        # Step 1: Upload document
        filename = f"notes_{uuid.uuid4().hex[:8]}.md"
        response = client.post(
            "/documents/upload",
            data={"collection_id": str(collection_id)},
            files={
                "file": (filename, b"# Alpha document\n\nshared document content for vector test\n", "text/markdown")
            },
        )
        assert response.status_code == 200, response.text
        document_id = response.json()["id"]

    # Verify ResourceIndex created with pending status
    async with session_factory() as session:
        index_service = ResourceIndexService(tenant_id=tenant_id, db_session=session)
        pending_items = await index_service.list_pending_items()
        doc_pending = [item for item in pending_items if item.resource_id == document_id]
        assert len(doc_pending) == 1, "Document should have pending ResourceIndex"

    await _parse_pending_documents(task_context)

    # Step 2: Call sync_to_vector_db
    result = await sync_to_vector_db(task_context=task_context, mode="incremental")
    assert result.outcome == "success"
    assert result.data["total_synced"] >= 1

    # Step 3: Verify vector presence
    async def assert_vector_present():
        chunks = await manager.get_context_chunks_by_resource(
            resource_id=document_id, resource_type=RAGSourceType.DOCUMENT.value, chunk_index=0, context_range=10
        )
        assert len(chunks) >= 1

    await _wait_until(assert_vector_present)

    # Verify ResourceIndex status updated
    async with session_factory() as session:
        index_service = ResourceIndexService(tenant_id=tenant_id, db_session=session)
        doc_index = await index_service.get_by_resource("document", document_id)
        assert doc_index.vector_status == VectorStatus.INDEXED

    # Step 4: Delete document
    with TestClient(app) as client:
        delete_response = client.delete("/documents", params=[("doc_ids", str(document_id))])
        assert delete_response.status_code == 200, delete_response.text

    # Step 5: Sync again - should clean up orphaned vector
    result = await sync_to_vector_db(task_context=task_context, mode="incremental")

    # Verify vector deleted
    async def assert_vector_deleted():
        chunks = await manager.get_context_chunks_by_resource(
            resource_id=document_id, resource_type=RAGSourceType.DOCUMENT.value, chunk_index=0, context_range=10
        )
        assert chunks == []

    await _wait_until(assert_vector_deleted)


async def test_document_blocks_manifest_sync_to_vector_db_e2e(vector_sync_e2e_env):
    """Upload → parse to blocks.json → manifest pointer → block-aware vector sync."""
    from fastapi.testclient import TestClient

    session_factory = vector_sync_e2e_env["session_factory"]
    tenant_id = vector_sync_e2e_env["tenant_id"]
    collection_id = vector_sync_e2e_env["collection_id"]
    task_context = vector_sync_e2e_env["task_context"]
    embeddings = vector_sync_e2e_env["embeddings"]
    file_storage = vector_sync_e2e_env["file_storage"]

    manager = RAGManager(tenant_id=tenant_id, embeddings=embeddings)
    markdown_body = "\n".join(
        [
            "# Quarterly Report",
            "",
            "Revenue grew across all regions.",
            "",
            "| Region | Revenue |",
            "| --- | --- |",
            "| North | 120 |",
        ]
    )

    with TestClient(app) as client:
        filename = f"report_{uuid.uuid4().hex[:8]}.md"
        response = client.post(
            "/documents/upload",
            data={"collection_id": str(collection_id)},
            files={"file": (filename, markdown_body.encode("utf-8"), "text/markdown")},
        )
        assert response.status_code == 200, response.text
        document_id = response.json()["id"]

    await _parse_pending_documents(task_context)

    async with session_factory() as session:
        index_service = ResourceIndexService(tenant_id=tenant_id, db_session=session)
        doc_index = await index_service.get_by_resource("document", document_id)
        assert doc_index is not None
        assert doc_index.raw_content.get("storage_uri")

        from apps.shared.document.manifest import get_storage_uri, is_manifest_pointer, read_blocks_json

        assert is_manifest_pointer(doc_index.raw_content)
        parser_name = doc_index.raw_content.get("meta", {}).get("parser")
        assert parser_name
        storage_uri = get_storage_uri(doc_index.raw_content)
        blocks_document = await read_blocks_json(file_storage, storage_uri, tenant_id=tenant_id)
        assert blocks_document.get("parser") == parser_name
        assert blocks_document.get("blocks")
        assert any(block.get("type") == "text" for block in blocks_document["blocks"])
        block_text = " ".join(str(block.get("text") or "") for block in blocks_document["blocks"])
        assert "North" in block_text

    result = await sync_to_vector_db(task_context=task_context, mode="incremental")
    assert result.outcome == "success"

    async def assert_block_aware_chunks():
        chunks = await manager.get_context_chunks_by_resource(
            resource_id=document_id,
            resource_type=RAGSourceType.DOCUMENT.value,
            chunk_index=0,
            context_range=10,
        )
        assert chunks
        assert any("north" in chunk.page_content for chunk in chunks)
        assert any(chunk.metadata.get("block_type") for chunk in chunks)
        assert all(chunk.metadata.get("source_parser") == parser_name for chunk in chunks)

    await _wait_until(assert_block_aware_chunks)


async def test_asset_sync_to_vector_db_e2e(vector_sync_e2e_env):
    """Test asset upload → ResourceIndex (pending) → sync_to_vector_db → Vector DB."""
    from fastapi.testclient import TestClient

    session_factory = vector_sync_e2e_env["session_factory"]
    tenant_id = vector_sync_e2e_env["tenant_id"]
    collection_id = vector_sync_e2e_env["collection_id"]
    data_source_id = vector_sync_e2e_env["data_source_id"]
    task_context = vector_sync_e2e_env["task_context"]
    embeddings = vector_sync_e2e_env["embeddings"]

    manager = RAGManager(tenant_id=tenant_id, embeddings=embeddings)

    with TestClient(app) as client:
        # Step 1: Upload asset
        asset_name = f"orders_{uuid.uuid4().hex[:8]}"
        response = client.post(
            f"/data-sources/{data_source_id}/assets/upload-csv",
            data={"asset_name": asset_name, "description": "alpha asset integration test"},
            files={"file": (f"{asset_name}.csv", b"id,name\n1,alpha\n2,beta\n", "text/csv")},
        )
        assert response.status_code == 201, response.text
        asset_id = response.json()["id"]

    # Verify ResourceIndex created
    async with session_factory() as session:
        index_service = ResourceIndexService(tenant_id=tenant_id, db_session=session)
        pending_items = await index_service.list_pending_items()
        asset_pending = [item for item in pending_items if item.resource_id == asset_id]
        assert len(asset_pending) == 1, "Asset should have pending ResourceIndex"

    # Step 2: Sync to vector DB
    result = await sync_to_vector_db(task_context=task_context, mode="incremental")
    assert result.outcome == "success"
    assert result.data["total_synced"] >= 1

    # Step 3: Verify vector presence
    async def assert_vector_present():
        chunks = await manager.get_context_chunks_by_resource(
            resource_id=asset_id, resource_type=RAGSourceType.ASSET.value, chunk_index=0, context_range=10
        )
        assert len(chunks) >= 1

    await _wait_until(assert_vector_present)

    # Step 3b: SearchService should surface synced asset via vector/hybrid path
    async with session_factory() as session:
        search_service = SearchService(
            tenant_id=tenant_id,
            session=session,
            user_id=vector_sync_e2e_env["user_id"],
            user_role="admin",
        )
        search_service.rag_manager = RAGManager(tenant_id=tenant_id, embeddings=embeddings)
        items, _pagination = await search_service.search_assets(query="alpha", page=1, page_size=10)

    matching = [item for item in items if item.resource_id == asset_id]
    assert matching, "Synced asset should appear in search results"
    assert matching[0].source in {"vector", "hybrid"}, (
        f"Expected vector/hybrid source, got {matching[0].source!r}"
    )

    # Step 4: Delete asset
    with TestClient(app) as client:
        delete_response = client.delete(
            f"/data-sources/{data_source_id}/assets",
            params=[("asset_names", asset_name)],
        )
        assert delete_response.status_code == 200, delete_response.text

    # Step 5: Sync to clean up
    await sync_to_vector_db(task_context=task_context, mode="incremental")

    # Verify vector deleted
    async def assert_vector_deleted():
        chunks = await manager.get_context_chunks_by_resource(
            resource_id=asset_id, resource_type=RAGSourceType.ASSET.value, chunk_index=0, context_range=10
        )
        assert chunks == []

    await _wait_until(assert_vector_deleted)


async def test_api_connector_sync_to_vector_db_e2e(vector_sync_e2e_env):
    """Test API operation creation → ResourceIndex (pending) → sync_to_vector_db → Vector DB."""
    from fastapi.testclient import TestClient

    session_factory = vector_sync_e2e_env["session_factory"]
    tenant_id = vector_sync_e2e_env["tenant_id"]
    collection_id = vector_sync_e2e_env["collection_id"]
    task_context = vector_sync_e2e_env["task_context"]
    embeddings = vector_sync_e2e_env["embeddings"]

    manager = RAGManager(tenant_id=tenant_id, embeddings=embeddings)

    with TestClient(app) as client:
        # Step 1: Create API connector + operation
        connector_name = f"orders-api-{uuid.uuid4().hex[:8]}"
        create_connector_response = client.post(
            "/api-connectors",
            json={
                "name": connector_name,
                "description": "integration connector",
                "base_url": "https://example.test",
                "auth_type": "none",
                "auth_config": {},
                "rate_policy": {},
                "schema_source_type": "manual",
                "schema_source_url": None,
            },
        )
        assert create_connector_response.status_code == 201, create_connector_response.text
        connector_id = create_connector_response.json()["id"]

        create_operation_response = client.post(
            f"/api-connectors/{connector_id}/operations",
            json={
                "method": "GET",
                "path_template": "/orders/{id}",
                "operation_id": f"get_order_{uuid.uuid4().hex[:6]}",
                "summary": "alpha operation summary",
                "description": "shared operation description",
                "tags": ["orders", "alpha"],
                "request_schema": {"type": "object"},
                "response_schema": {"type": "object"},
                "auth_requirement": "required",
                "risk_level": "medium",
            },
        )
        assert create_operation_response.status_code == 201, create_operation_response.text
        operation_id = create_operation_response.json()["id"]

    # Verify ResourceIndex created
    async with session_factory() as session:
        index_service = ResourceIndexService(tenant_id=tenant_id, db_session=session)
        pending_items = await index_service.list_pending_items()
        op_pending = [item for item in pending_items if item.resource_id == operation_id]
        assert len(op_pending) == 1, "API operation should have pending ResourceIndex"

    # Step 2: Sync to vector DB
    result = await sync_to_vector_db(task_context=task_context, mode="incremental")
    assert result.outcome == "success"
    assert result.data["total_synced"] >= 1

    # Step 3: Verify vector presence
    async def assert_vector_present():
        chunks = await manager.get_context_chunks_by_resource(
            resource_id=operation_id,
            resource_type=RAGSourceType.API_CONNECTOR.value,
            chunk_index=0,
            context_range=10,
        )
        assert len(chunks) >= 1

    await _wait_until(assert_vector_present)

    # Step 4: Delete operation
    with TestClient(app) as client:
        delete_response = client.delete(f"/api-connectors/operations/{operation_id}")
        assert delete_response.status_code == 204, delete_response.text

    # Step 5: Sync to clean up
    await sync_to_vector_db(task_context=task_context, mode="incremental")

    # Verify vector deleted
    async def assert_vector_deleted():
        chunks = await manager.get_context_chunks_by_resource(
            resource_id=operation_id,
            resource_type=RAGSourceType.API_CONNECTOR.value,
            chunk_index=0,
            context_range=10,
        )
        assert chunks == []

    await _wait_until(assert_vector_deleted)


async def test_full_rebuild_mode_e2e(vector_sync_e2e_env):
    """Test full rebuild mode: marks all vectors stale and re-indexes."""
    from fastapi.testclient import TestClient

    session_factory = vector_sync_e2e_env["session_factory"]
    tenant_id = vector_sync_e2e_env["tenant_id"]
    collection_id = vector_sync_e2e_env["collection_id"]
    task_context = vector_sync_e2e_env["task_context"]
    embeddings = vector_sync_e2e_env["embeddings"]

    manager = RAGManager(tenant_id=tenant_id, embeddings=embeddings)

    # Upload a document
    with TestClient(app) as client:
        filename = f"rebuild_{uuid.uuid4().hex[:8]}.md"
        response = client.post(
            "/documents/upload",
            data={"collection_id": str(collection_id)},
            files={"file": (filename, b"# Rebuild test\n\ncontent for rebuild\n", "text/markdown")},
        )
        assert response.status_code == 200
        document_id = response.json()["id"]

    await _parse_pending_documents(task_context)

    # First sync
    result = await sync_to_vector_db(task_context=task_context, mode="incremental")
    assert result.data["total_synced"] >= 1

    # Verify synced
    async with session_factory() as session:
        index_service = ResourceIndexService(tenant_id=tenant_id, db_session=session)
        doc_index = await index_service.get_by_resource("document", document_id)
        assert doc_index.vector_status == VectorStatus.INDEXED

    # Manually mark as stale to simulate embedding model change
    async with session_factory() as session:
        index_service = ResourceIndexService(tenant_id=tenant_id, db_session=session)
        await index_service.mark_all_vectors_stale()
        await session.commit()

    # Verify stale
    async with session_factory() as session:
        index_service = ResourceIndexService(tenant_id=tenant_id, db_session=session)
        doc_index = await index_service.get_by_resource("document", document_id)
        assert doc_index.vector_status == VectorStatus.STALE

    # Full rebuild
    result = await sync_to_vector_db(task_context=task_context, mode="full")
    assert result.outcome == "success"

    # Verify re-synced
    async with session_factory() as session:
        index_service = ResourceIndexService(tenant_id=tenant_id, db_session=session)
        doc_index = await index_service.get_by_resource("document", document_id)
        assert doc_index.vector_status == VectorStatus.INDEXED

    # Cleanup
    with TestClient(app) as client:
        client.delete("/documents", params=[("doc_ids", str(document_id))])
    await sync_to_vector_db(task_context=task_context, mode="incremental")


async def test_cleanup_orphaned_vectors_e2e(vector_sync_e2e_env):
    """Test orphaned vector detection and cleanup.

    Orphans can occur when:
    - Delete succeeds on DB but fails on Vector DB
    - Process crashes during delete operation
    """
    from fastapi.testclient import TestClient

    session_factory = vector_sync_e2e_env["session_factory"]
    tenant_id = vector_sync_e2e_env["tenant_id"]
    collection_id = vector_sync_e2e_env["collection_id"]
    task_context = vector_sync_e2e_env["task_context"]
    embeddings = vector_sync_e2e_env["embeddings"]

    manager = RAGManager(tenant_id=tenant_id, embeddings=embeddings)

    # Upload and sync a document
    with TestClient(app) as client:
        filename = f"orphan_{uuid.uuid4().hex[:8]}.md"
        response = client.post(
            "/documents/upload",
            data={"collection_id": str(collection_id)},
            files={"file": (filename, b"# Orphan test\n\ncontent for orphan test\n", "text/markdown")},
        )
        assert response.status_code == 200
        document_id = response.json()["id"]

    await _parse_pending_documents(task_context)
    await sync_to_vector_db(task_context=task_context, mode="incremental")

    # Verify vector exists
    async def assert_vector_present():
        chunks = await manager.get_context_chunks_by_resource(
            resource_id=document_id, resource_type=RAGSourceType.DOCUMENT.value, chunk_index=0, context_range=10
        )
        assert len(chunks) >= 1

    await _wait_until(assert_vector_present)

    # Simulate orphan: delete from DB but NOT from vector store
    async with session_factory() as session:
        # Delete ResourceIndex directly (simulating partial failure)
        index_service = ResourceIndexService(tenant_id=tenant_id, db_session=session)
        await index_service.delete("document", document_id)
        await session.commit()

    # Delete the document record too
    async with session_factory() as session:
        doc = await session.get(Document, document_id)
        if doc:
            await session.delete(doc)
            await session.commit()

    # Vector should still exist (orphaned)
    chunks = await manager.get_context_chunks_by_resource(
        resource_id=document_id, resource_type=RAGSourceType.DOCUMENT.value, chunk_index=0, context_range=10
    )
    # Note: Chroma may still have the vector even though ResourceIndex is deleted

    # Run orphan cleanup (dry run first)
    dry_run_result = await cleanup_orphaned_vectors(task_context=task_context, dry_run=True)
    assert dry_run_result.data["dry_run"] is True

    # Run actual cleanup
    cleanup_result = await cleanup_orphaned_vectors(task_context=task_context, dry_run=False)
    assert cleanup_result.outcome == "success"
