from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from random import randint
from typing import Any, Callable
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from apps.shared.api_connector.domain import RatePolicyDomain
from apps.shared.api_connector.service import ApiConnectorService
from apps.shared.authz.authz_query_builder import AuthzSqlFilter
from apps.shared.core.auth import get_current_user
from apps.shared.data_source.schemas import RAGSourceType
from apps.shared.data_source.service import AssetAccessScope
from apps.shared.document.collection_service import DocumentAccessScope
from apps.shared.db.models import AssetMetadata, DataSource, Document, DocumentCollection, Tenant, User
from apps.shared.db.session import get_db
from apps.shared.domain.actor import ActorContext
from apps.shared.infra.rag.index_payload import IndexRecordPayload, IndexUpsertPayload
from apps.shared.infra.rag.rag_manager import RAGManager
from apps.shared.schemas.user import UserDTO
from apps.shared.search.schemas import ResourceIndexCreateDTO
from apps.shared.search.search_service import SearchService
from apps.tenant_app_service.server import app
from tests.integration.search_quality_test_utils import (
    assert_column_exists,
    assert_index_exists,
    resolve_top_n_for_mode,
    write_search_quality_result,
)

BENCHMARK_DATA_PATH = Path(__file__).parent / "fixtures" / "search_quality_benchmark.json"


@dataclass
class QueryTopNExpectation:
    case_id: str
    query: str
    expected_source_id: str
    top_n: int | None
    top_n_by_mode: dict[str, Any] | None


def _load_benchmark_data() -> dict[str, Any]:
    with BENCHMARK_DATA_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _configure_api_search_mode(monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    async def _mock_api_connector_abac_filter(self):
        return AuthzSqlFilter(allow_all=True, deny_all=False, clause=None)

    monkeypatch.setattr(SearchService, "_get_api_connector_authz_filter", _mock_api_connector_abac_filter)

    if mode == "fts":

        async def _mock_vector_empty(self, query: str, k: int, scoped_connector_ids=None, authz_filter=None):
            return []

        monkeypatch.setattr(SearchService, "_search_api_connectors_vector", _mock_vector_empty)
        return

    if mode == "vector":

        async def _mock_fts_empty(
            self,
            query: str,
            k: int,
            scoped_connector_ids: list[int] | None = None,
            authz_filter=None,
        ):
            return []

        monkeypatch.setattr(SearchService, "_search_api_connectors_fts", _mock_fts_empty)


def _configure_document_search_mode(monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    async def _mock_document_access_scope(self):
        return DocumentAccessScope(
            deny_all=False,
            allow_all=True,
            document_filter=None,
            index_parent_filter=None,
        )

    monkeypatch.setattr(SearchService, "_get_document_access_scope", _mock_document_access_scope)

    if mode == "fts":

        async def _mock_doc_vector_empty(self, query: str, k: int, abac_filter=None):
            return []

        monkeypatch.setattr(SearchService, "_search_documents_vector", _mock_doc_vector_empty)
    elif mode == "vector":

        async def _mock_doc_fts_empty(self, query: str, k: int, abac_filter=None):
            return []

        monkeypatch.setattr(SearchService, "_search_documents_fts", _mock_doc_fts_empty)


def _configure_asset_search_mode(monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    async def _mock_asset_access_scope(self):
        return AssetAccessScope(
            deny_all=False,
            allow_all=True,
            asset_filter=None,
            index_parent_filter=None,
        )

    monkeypatch.setattr(SearchService, "_get_asset_access_scope", _mock_asset_access_scope)

    if mode == "fts":

        async def _mock_asset_vector_empty(self, query: str, k: int, asset_abac_filter=None):
            return []

        monkeypatch.setattr(SearchService, "_search_assets_vector", _mock_asset_vector_empty)
    elif mode == "vector":

        async def _mock_asset_fts_empty(self, query: str, k: int, index_abac_filter=None):
            return []

        monkeypatch.setattr(SearchService, "_search_assets_fts", _mock_asset_fts_empty)


RESOURCE_SPECS: dict[str, dict[str, Any]] = {
    "api_connector": {
        "source": "api_connector",
        "item_type": "api_connector",
        "configure_mode": _configure_api_search_mode,
    },
    "document": {
        "source": "document",
        "item_type": "document",
        "configure_mode": _configure_document_search_mode,
    },
    "asset": {
        "source": "asset",
        "item_type": "asset",
        "configure_mode": _configure_asset_search_mode,
    },
}


@pytest_asyncio.fixture
async def search_quality_benchmark_env(async_db_session: AsyncSession):
    benchmark = _load_benchmark_data()
    api_benchmark = benchmark["api_connector"]
    doc_benchmark = benchmark["document"]
    asset_benchmark = benchmark["asset_metadata"]

    session_url = async_db_session.bind.engine.url.render_as_string(hide_password=False)
    test_engine = create_async_engine(session_url, future=True, poolclass=NullPool)
    test_session_local = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async with test_session_local() as schema_session:
        await assert_column_exists(schema_session, "api_operation_index", "search_vector")
        await assert_index_exists(schema_session, "idx_api_operation_search_vector")
        await assert_column_exists(schema_session, "asset_metadata", "search_vector")
        await assert_index_exists(schema_session, "idx_asset_metadata_search_vector")

    async def override_get_db():
        async with test_session_local() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    suffix = uuid4().hex[:8]
    async with test_session_local() as seed_session:
        tenant = Tenant(name=f"search-quality-{suffix}", slug=f"search-quality-{suffix}", status="active")
        seed_session.add(tenant)
        await seed_session.flush()

        user = User(
            username=f"search_quality_user_{suffix}",
            email=f"search_quality_{suffix}@test.local",
            hashed_password="hashed",
            role="admin",
            tenant_id=tenant.id,
            status="active",
        )
        seed_session.add(user)
        await seed_session.flush()

        document_collection = DocumentCollection(
            tenant_id=tenant.id,
            name="search-quality-benchmark",
            owner_id=user.id,
            description="Benchmark document collection",
        )
        seed_session.add(document_collection)
        await seed_session.flush()

        service = ApiConnectorService(tenant_id=tenant.id, db_session=seed_session)
        connector = await service.create_connector(
            owner_id=user.id,
            name="quality-connector",
            description="connector for search quality benchmark",
            base_url="https://8.8.8.8",
            auth_type="none",
            auth_config={},
            rate_policy=RatePolicyDomain.from_raw({}),
            schema_source_type="manual",
            schema_source_url=None,
        )

        api_case_to_id: dict[str, int] = {}
        for case in api_benchmark["cases"]:
            content = case["content"]
            created = await service.add_manual_operation_for_actor(
                connector_id=connector.id,
                actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
                method=content["method"],
                path_template=content["path_template"],
                operation_id=content["operation_id"],
                summary=content["summary"],
                description=content.get("description"),
                tags=content.get("tags") or [],
                request_schema={"type": "object"},
                response_schema={"type": "object"},
            )
            api_case_to_id[case["case_id"]] = created.id

        from apps.shared.search.indexing_service import ResourceIndexService

        indexing_svc = ResourceIndexService(tenant_id=tenant.id, db_session=seed_session)
        await seed_session.commit()
        await indexing_svc.sync_all_pending()

        document_case_to_id: dict[str, int] = {}
        document_vector_payloads: list[IndexUpsertPayload] = []
        for case in doc_benchmark.get("cases", []):
            content = case["content"]
            raw_file_url = content.get("file_url")
            raw_vector_text = content.get("vector_text")
            if not raw_file_url and not raw_vector_text:
                raise ValueError(
                    f"document benchmark case '{case.get('case_id', 'unknown')}' "
                    "must provide at least one of: file_url or vector_text"
                )

            file_url = raw_file_url or f"s3://benchmark/{suffix}/{content['filename']}"
            vector_text = raw_vector_text or content.get("preview_text") or content["filename"]
            doc_vector_ref_id = str(uuid4())

            doc = Document(
                tenant_id=tenant.id,
                collection_id=document_collection.id,
                filename=content["filename"],
                file_url=file_url,
                file_size=int(content.get("file_size", 1024)),
                file_hash="hash" + str(randint(1, 1000000)),
                status="active",
                owner_id=user.id,
            )
            seed_session.add(doc)
            await seed_session.flush()
            document_case_to_id[case["case_id"]] = doc.id

            # Create ResourceIndex for FTS search
            await indexing_svc.create_or_update(
                ResourceIndexCreateDTO(
                    tenant_id=tenant.id,
                    resource_type="document",
                    resource_id=doc.id,
                    owner_id=user.id,
                    raw_content={"text": vector_text, "meta": {"filename": content["filename"]}},
                    parent_id=document_collection.id,
                )
            )

            document_vector_payloads.append(
                IndexUpsertPayload(
                    records=[
                        IndexRecordPayload(
                            content=vector_text,
                            metadata={
                                "tenant_id": tenant.id,
                                "source_type": RAGSourceType.DOCUMENT.value,
                                "resource_type": "document",
                                "resource_id": doc.id,
                                "doc_id": doc.id,
                                "filename": doc.filename,
                                "file_url": doc.file_url,
                                "vector_ref_id": doc_vector_ref_id,
                                "chunk_index": 0,
                                "total_chunks": 1,
                            },
                        )
                    ],
                )
            )

        data_source = DataSource(
            tenant_id=tenant.id,
            name=f"benchmark-ds-{suffix}",
            type="postgres",
            managed=True,
            config={},
            description="benchmark datasource",
            owner_id=user.id,
            asset_count=0,
        )
        seed_session.add(data_source)
        await seed_session.flush()

        asset_case_to_id: dict[str, int] = {}
        asset_vector_payloads: list[IndexUpsertPayload] = []
        for case in asset_benchmark.get("cases", []):
            content = case["content"]
            description = content["description"]
            asset_vector_ref_id = str(uuid4())
            asset = AssetMetadata(
                data_source_id=data_source.id,
                asset_name=content["asset_name"],
                asset_type=content["asset_type"],
                columns=content["columns"],
                meta={"description": description, "column_description": {}},
                meta_override={},
                owner_id=user.id,
                row_count=100,
                source_info={"kind": "benchmark"},
            )
            seed_session.add(asset)
            await seed_session.flush()
            asset_case_to_id[case["case_id"]] = asset.id

            # Create ResourceIndex for FTS search
            columns_text = ", ".join(col.get("name", "") for col in content.get("columns", []))
            asset_text = content.get("vector_text") or f"{content['asset_name']} {description} {columns_text}".strip()
            await indexing_svc.create_or_update(
                ResourceIndexCreateDTO(
                    tenant_id=tenant.id,
                    resource_type="asset",
                    resource_id=asset.id,
                    owner_id=user.id,
                    raw_content={
                        "text": asset_text,
                        "meta": {"asset_name": content["asset_name"], "asset_type": content["asset_type"]},
                    },
                    parent_id=data_source.id,
                )
            )

            asset_vector_payloads.append(
                IndexUpsertPayload(
                    records=[
                        IndexRecordPayload(
                            content=asset_text,
                            metadata={
                                "tenant_id": tenant.id,
                                "source_type": RAGSourceType.ASSET.value,
                                "resource_type": "asset",
                                "resource_id": asset.id,
                                "asset_id": asset.id,
                                "data_source_id": data_source.id,
                                "asset_name": asset.asset_name,
                                "asset_type": asset.asset_type,
                                "vector_ref_id": asset_vector_ref_id,
                                "chunk_index": 0,
                                "total_chunks": 1,
                            },
                        )
                    ],
                )
            )

        data_source.asset_count = len(asset_case_to_id)

        # Sync all ResourceIndex records to populate tokenized_content for FTS
        await indexing_svc.sync_all_pending()

        rag_manager = RAGManager(tenant_id=tenant.id)
        await rag_manager.clear_by_source_type(RAGSourceType.DOCUMENT.value)
        await rag_manager.clear_by_source_type(RAGSourceType.ASSET.value)
        from langchain_core.documents import Document as LangChainDocument

        for payload in document_vector_payloads:
            await rag_manager.add_chunks(
                [LangChainDocument(page_content=r.content, metadata=r.metadata) for r in payload.records]
            )
        for payload in asset_vector_payloads:
            await rag_manager.add_chunks(
                [LangChainDocument(page_content=r.content, metadata=r.metadata) for r in payload.records]
            )

        await seed_session.commit()

    expectations: dict[str, list[QueryTopNExpectation]] = {
        "api_connector": [],
        "document": [],
        "asset": [],
    }

    for case in api_benchmark["cases"]:
        expected_id = api_case_to_id[case["case_id"]]
        for query_item in case.get("queries", []):
            expectations["api_connector"].append(
                QueryTopNExpectation(
                    case_id=case["case_id"],
                    query=query_item["keyword"],
                    expected_source_id=str(expected_id),
                    top_n=query_item.get("top_n"),
                    top_n_by_mode=query_item.get("top_n_by_mode"),
                )
            )

    for case in doc_benchmark.get("cases", []):
        expected_id = str(document_case_to_id[case["case_id"]])
        for query_item in case.get("queries", []):
            expectations["document"].append(
                QueryTopNExpectation(
                    case_id=case["case_id"],
                    query=query_item["keyword"],
                    expected_source_id=expected_id,
                    top_n=query_item.get("top_n"),
                    top_n_by_mode=query_item.get("top_n_by_mode"),
                )
            )

    for case in asset_benchmark.get("cases", []):
        expected_id = str(asset_case_to_id[case["case_id"]])
        for query_item in case.get("queries", []):
            expectations["asset"].append(
                QueryTopNExpectation(
                    case_id=case["case_id"],
                    query=query_item["keyword"],
                    expected_source_id=expected_id,
                    top_n=query_item.get("top_n"),
                    top_n_by_mode=query_item.get("top_n_by_mode"),
                )
            )

    user_ctx = {
        "value": UserDTO(
            id=user.id,
            username=user.username,
            role=user.role,
            tenant_id=tenant.id,
            tenant_name=tenant.name,
        )
    }

    async def override_user():
        return user_ctx["value"]

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_user

    env = {
        "client": TestClient(app),
        "expectations": expectations,
        "defaults": {
            "api_connector": {
                "default_top_n": api_benchmark.get("default_top_n"),
                "default_top_n_by_mode": api_benchmark.get("default_top_n_by_mode"),
            },
            "document": {
                "default_top_n": doc_benchmark.get("default_top_n"),
                "default_top_n_by_mode": doc_benchmark.get("default_top_n_by_mode"),
            },
            "asset": {
                "default_top_n": asset_benchmark.get("default_top_n"),
                "default_top_n_by_mode": asset_benchmark.get("default_top_n_by_mode"),
            },
        },
    }

    yield env

    app.dependency_overrides.clear()
    await test_engine.dispose()


def execute_topn_cases(
    *,
    env: dict[str, Any],
    resource: str,
    search_mode: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = RESOURCE_SPECS[resource]
    defaults = env["defaults"][resource]
    expectations: list[QueryTopNExpectation] = env["expectations"][resource]
    client: TestClient = env["client"]

    configure_mode: Callable[[pytest.MonkeyPatch, str], None] = spec["configure_mode"]
    configure_mode(monkeypatch, search_mode)

    for item in expectations:
        top_n = resolve_top_n_for_mode(
            mode=search_mode,
            query_top_n=item.top_n,
            query_top_n_by_mode=item.top_n_by_mode,
            default_top_n=defaults["default_top_n"],
            default_top_n_by_mode=defaults["default_top_n_by_mode"],
        )

        resp = client.get(
            "/search",
            params={
                "query": item.query,
                "sources": spec["source"],
                "page_size": top_n,
            },
        )
        assert resp.status_code == 200

        payload = resp.json()
        ranked_ids = [
            str(result["resource_id"]) for result in payload["items"] if result["resource_type"] == spec["item_type"]
        ]

        found_rank = None
        for idx, resource_id in enumerate(ranked_ids[:top_n], start=1):
            if resource_id == item.expected_source_id:
                found_rank = idx
                break

        passed = found_rank is not None
        write_search_quality_result(
            resource=resource,
            mode=search_mode,
            case_id=item.case_id,
            query=item.query,
            expected_source_id=item.expected_source_id,
            top_n=top_n,
            found_rank=found_rank,
            passed=passed,
        )

        assert passed, (
            f"Expected {resource} case '{item.case_id}' to appear in top {top_n} for query={item.query!r} "
            f"({search_mode}), but ranked_ids={ranked_ids}"
        )
