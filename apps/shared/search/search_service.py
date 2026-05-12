"""Unified Search Service for documents, assets, and API connector metadata.

Provides hybrid search combining:
- PostgreSQL FTS (fast keyword/metadata search) via ResourceIndex JOIN source tables
- Vector similarity (semantic search) via RAGManager with post-filtering for ABAC/ACL
"""

from typing import Any

from langchain_core.documents import Document
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.api_connector.repository import ApiConnectorRepository, ApiOperationIndexRepository
from apps.shared.authz.authz_query_builder import AuthzSqlFilter, build_unified_resource_filter
from apps.shared.authz.delegation import combine_agent_scope, filter_explicit_deny_ids
from apps.shared.core.base_service import TenantAwareService
from apps.shared.core.exceptions import ResourceNotFoundError, ValidationError
from apps.shared.data_source.adapters import db_asset_metadata_to_domain
from apps.shared.data_source.repository import AssetMetadataRepository, DataSourceRepository
from apps.shared.data_source.schemas import RAGSourceType
from apps.shared.data_source.service import AssetAccessScope, DataSourceService
from apps.shared.db.models import ApiConnector, AssetMetadata, ResourceIndex
from apps.shared.db.models import Document as DocumentModel
from apps.shared.document.collection_service import DocumentAccessScope, DocumentCollectionService
from apps.shared.document.schemas import DocumentChunk, DocumentSearchResult
from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import (
    ABAC_ACTION_READ,
    RESOURCE_TYPE_API_CONNECTOR,
    RESOURCE_TYPE_ASSET,
    RESOURCE_TYPE_DATA_SOURCE,
    RESOURCE_TYPE_DOCUMENT,
    RESOURCE_TYPE_DOCUMENT_COLLECTION,
    SearchableResourceType,
)
from apps.shared.infra.rag import RAGManager
from apps.shared.infra.rag.embedding_utils import create_embeddings_from_config
from apps.shared.infra.rag.metadata_keys import META_RESOURCE_ID
from apps.shared.search.parser import prepare_search_queries
from apps.shared.search.repository import ResourceIndexRepository
from apps.shared.search.schemas import (
    ApiConnectorSearchResult,
    AssetSearchResult,
    DocumentSearchChunkHint,
    ResourceContextChunk,
    SearchResultItem,
    SearchTarget,
)
from apps.shared.utils.logger import get_logger
from apps.shared.utils.pagination import PaginationRequest

logger = get_logger(__name__)

ALLOWED_SEARCH_SOURCES: tuple[SearchableResourceType, ...] = (
    SearchTarget.DOCUMENT,
    SearchTarget.ASSET,
    SearchTarget.API_CONNECTOR,
)

MAX_DOCUMENT_SEARCH_CHUNK_HINTS = 3
MAX_DOCUMENT_CONTEXT_ANCHORS = 3
MAX_PAGE_CONTEXT_CHUNKS = 200


def _chunk_metadata(document) -> dict:
    return document.metadata if isinstance(document.metadata, dict) else {}


def _document_chunk_from_vector(document, *, relevance: float | None = None) -> DocumentChunk:
    metadata = _chunk_metadata(document)
    page = metadata.get("page")
    block_type = metadata.get("block_type")
    image_uri = metadata.get("image_uri")
    return DocumentChunk(
        chunk_index=metadata.get("chunk_index", 0),
        content=document.page_content,
        relevance=relevance,
        page=page if isinstance(page, int) else None,
        block_type=block_type if isinstance(block_type, str) else None,
        image_uri=image_uri if isinstance(image_uri, str) else None,
    )


def _context_chunk(document) -> ResourceContextChunk:
    metadata = _chunk_metadata(document)
    page = metadata.get("page")
    block_type = metadata.get("block_type")
    image_uri = metadata.get("image_uri")
    return ResourceContextChunk(
        chunk_index=metadata.get("chunk_index"),
        total_chunks=metadata.get("total_chunks"),
        content=document.page_content,
        block_type=block_type if isinstance(block_type, str) else None,
        image_uri=image_uri if isinstance(image_uri, str) else None,
        page=page if isinstance(page, int) else None,
    )


def document_image_public_url(resource_id: int, image_uri: str) -> str:
    filename = image_uri.rsplit("/", 1)[-1]
    return f"/documents/{resource_id}/images/{filename}"


def finalize_document_context_chunk(chunk: ResourceContextChunk, resource_id: int) -> ResourceContextChunk:
    """Expose cite-ready image fields and hide internal storage URIs."""
    if chunk.block_type == "image" and chunk.image_uri:
        image_url = document_image_public_url(resource_id, chunk.image_uri)
        label = chunk.content or "Figure"
        return chunk.model_copy(
            update={
                "image_url": image_url,
                "image_markdown": f"![{label}]({image_url})",
            }
        )
    return chunk


def finalize_document_context_chunks(
    chunks: list[ResourceContextChunk],
    resource_id: int,
) -> list[ResourceContextChunk]:
    return [finalize_document_context_chunk(chunk, resource_id) for chunk in chunks]


class SearchService(TenantAwareService):
    """Unified search service for documents, assets, and API connectors."""

    def __init__(
        self,
        tenant_id: int,
        session: AsyncSession,
        user_id: int,
        user_role: str,
        tenant_config: dict | None = None,
        allowed_collection_ids: list[int] | None = None,
        allowed_data_source_ids: list[int] | None = None,
        allowed_api_connector_ids: list[int] | None = None,
        delegate: bool = False,
    ):
        super().__init__(tenant_id=tenant_id, db_session=session)
        self.session = session
        self.user_id = user_id
        self.user_role = user_role
        self.tenant_config = tenant_config
        self.allowed_collection_ids = allowed_collection_ids
        self.allowed_data_source_ids = allowed_data_source_ids
        self.allowed_api_connector_ids = allowed_api_connector_ids
        self.delegate = delegate
        embeddings = create_embeddings_from_config(tenant_config) if tenant_config else None
        self.rag_manager = RAGManager(tenant_id=tenant_id, embeddings=embeddings)
        self.asset_repo = AssetMetadataRepository(session)
        self.data_source_repo = DataSourceRepository(session)
        self.api_connector_repo = ApiConnectorRepository(session)
        self.api_operation_repo = ApiOperationIndexRepository(session)
        self.resource_index_repo = ResourceIndexRepository(session)

    @staticmethod
    def _truncate_snippet(text: str, limit: int = 300) -> str:
        if not text:
            return ""
        if len(text) <= limit:
            return text
        return f"{text[:limit].rstrip()}..."

    @staticmethod
    def _chunk_section_hint(content: str, limit: int = 80) -> str:
        normalized = " ".join((content or "").split())
        if not normalized:
            return ""
        if len(normalized) <= limit:
            return normalized
        return f"{normalized[:limit].rstrip()}..."

    def _top_document_chunks(self, chunks: list[DocumentChunk]) -> list[DocumentChunk]:
        if not chunks:
            return []
        ranked = sorted(
            chunks,
            key=lambda chunk: (-(chunk.relevance or 0.0), chunk.chunk_index),
        )
        seen: set[int] = set()
        selected: list[DocumentChunk] = []
        for chunk in ranked:
            if chunk.chunk_index in seen:
                continue
            seen.add(chunk.chunk_index)
            selected.append(chunk)
            if len(selected) >= MAX_DOCUMENT_SEARCH_CHUNK_HINTS:
                break
        return selected

    def _document_to_item(self, result: DocumentSearchResult) -> SearchResultItem:
        snippet = result.highlight or (result.chunks[0].content if result.chunks else "")
        contents: list[DocumentSearchChunkHint] = []
        for chunk in self._top_document_chunks(result.chunks):
            hint: DocumentSearchChunkHint = {
                "collection_id": result.collection_id,
                "chunk_index": chunk.chunk_index,
                "chunk_content": self._truncate_snippet(chunk.content),
                "section_hint": self._chunk_section_hint(chunk.content),
                "relevance": chunk.relevance,
            }
            if chunk.page is not None:
                hint["page"] = chunk.page
            if chunk.block_type:
                hint["block_type"] = chunk.block_type
            if chunk.image_uri:
                hint["image_url"] = document_image_public_url(result.doc_id, chunk.image_uri)
            contents.append(hint)
        if not contents:
            contents = [{"collection_id": result.collection_id}]
        return SearchResultItem(
            resource_type=RESOURCE_TYPE_DOCUMENT,
            resource_id=result.doc_id,
            title=result.filename,
            score=result.rrf_score,
            source=result.source,
            snippet=snippet,
            contents=contents,
        )

    def _asset_to_item(self, result: AssetSearchResult) -> SearchResultItem:
        desc = result.resolved_description
        snippet = f"{result.asset_name}: {desc}" if desc else result.asset_name
        contents = [
            {
                "asset_name": result.asset_name,
                "asset_type": result.asset_type,
                "column_names": [
                    col.get("name", "") for col in result.columns if isinstance(col, dict) and col.get("name")
                ],
                "column_count": len(result.columns) if result.columns else 0,
                "row_count": result.row_count,
                "data_source": {
                    "id": result.data_source_id,
                    "name": result.data_source_name,
                    "type": result.data_source_type,
                },
            }
        ]
        return SearchResultItem(
            resource_type=RESOURCE_TYPE_ASSET,
            resource_id=result.asset_id,
            title=result.asset_name,
            score=result.rrf_score,
            source=result.source,
            snippet=snippet,
            contents=contents,
        )

    def _api_connector_to_item(self, result: ApiConnectorSearchResult) -> SearchResultItem:
        snippet = result.summary or result.description or f"{result.method} {result.path_template}"
        title = f"{result.method} {result.path_template}"
        return SearchResultItem(
            resource_type=RESOURCE_TYPE_API_CONNECTOR,
            resource_id=result.operation_id,
            title=title,
            score=result.rrf_score,
            source=result.source,
            snippet=snippet,
            contents=[
                {
                    "operation_uid": result.operation_uid,
                    "connector_id": result.connector_id,
                    "connector_name": result.connector_name,
                    "method": result.method,
                    "path_template": result.path_template,
                    "summary": result.summary,
                    "description": result.description,
                    "tags": result.tags,
                }
            ],
        )

    async def search_for_actor(
        self,
        *,
        query: str,
        sources: list[SearchableResourceType],
        page: int,
        page_size: int,
    ) -> tuple[list[SearchResultItem], PaginationRequest]:
        if not sources:
            return [], PaginationRequest.with_total(page=page, page_size=page_size, total=0)
        invalid_sources = [s for s in sources if s not in ALLOWED_SEARCH_SOURCES]
        if invalid_sources:
            raise ValidationError(f"Unsupported sources: {invalid_sources}", details={"code": "INVALID_SOURCES"})
        fetch_window = page * page_size + 1
        unique_sources = list(dict.fromkeys(sources))
        items: list[SearchResultItem] = []
        if SearchTarget.DOCUMENT in unique_sources:
            docs, _ = await self.search_documents(query=query, page=1, page_size=fetch_window)
            items.extend(docs)
        if SearchTarget.ASSET in unique_sources:
            assets, _ = await self.search_assets(query=query, page=1, page_size=fetch_window)
            items.extend(assets)
        if SearchTarget.API_CONNECTOR in unique_sources:
            ops, _ = await self.search_api_connectors(query=query, page=1, page_size=fetch_window)
            items.extend(ops)
        items = sorted(items, key=lambda item: (-(item.score or 0), item.resource_type, str(item.resource_id)))
        total = len(items)
        pagination = PaginationRequest.with_total(page=page, page_size=page_size, total=total)
        return items[pagination.offset : pagination.end], pagination

    # ==================== Document Search ====================

    async def search_documents(
        self, query: str, page: int = 1, page_size: int = 10
    ) -> tuple[list[SearchResultItem], PaginationRequest]:
        raw_query = (query or "").strip()
        logger.info("Searching documents: query='%s...', page=%s, page_size=%s", raw_query[:50], page, page_size)
        access_scope = await self._get_document_access_scope()
        logger.info("Document search authz scope: %s", access_scope)
        if access_scope is not None and access_scope.deny_all:
            return [], PaginationRequest.with_total(page=page, page_size=page_size, total=0)
        params = PaginationRequest(page=page, page_size=page_size)
        start, end = params.offset, params.end
        fetch_end = end + 1
        fts_query, vector_query = prepare_search_queries(raw_query)
        index_filter = access_scope.index_parent_filter if access_scope else None
        document_filter = access_scope.document_filter if access_scope else None
        merged = await self._search_documents_hybrid(
            fts_query,
            vector_query,
            fetch_end,
            index_abac_filter=index_filter,
            document_abac_filter=document_filter,
        )
        page_items = merged[start:end]
        has_next = len(merged) > end
        total = (end + 1) if has_next else (start + len(page_items))
        return [self._document_to_item(d) for d in page_items], PaginationRequest.with_total(
            page=page, page_size=page_size, total=total
        )

    async def _search_documents_fts(self, query: str, k: int, index_abac_filter=None) -> list[DocumentSearchResult]:
        """FTS search for documents via ResourceIndex with collection authz pushdown.

        Authz is enforced on ResourceIndex.parent_id (= collection_id). Document rows
        are reloaded with collection filter as defense in depth.
        """
        ri_rows = await self.resource_index_repo.search_documents_fts(
            tenant_id=self.tenant_id, query=query, limit=k, abac_filter=index_abac_filter
        )
        if not ri_rows:
            return []

        # Build maps from FTS results (now includes snippet)
        doc_ids = [ri.resource_id for ri, _, _ in ri_rows]
        rank_map = {ri.resource_id: float(rank or 0) for ri, rank, _ in ri_rows}
        snippet_map = {ri.resource_id: snippet for ri, _, snippet in ri_rows}

        # Reload documents; index filter already scoped by collection parent_id
        stmt = select(DocumentModel).where(DocumentModel.tenant_id == self.tenant_id, DocumentModel.id.in_(doc_ids))
        result = await self.session.execute(stmt)
        docs = list(result.scalars().all())

        results = []
        for doc in docs:
            rank = rank_map.get(doc.id, 0)
            snippet = snippet_map.get(doc.id, "")
            # Use ts_headline snippet directly instead of fetching chunks from VectorDB
            doc_chunks = [
                DocumentChunk(
                    chunk_index=0,
                    content=snippet,
                    relevance=1.0,
                )
            ]
            results.append(
                DocumentSearchResult(
                    doc_id=doc.id,
                    collection_id=doc.collection_id,
                    filename=doc.filename,
                    rrf_score=rank,
                    source="fts",
                    chunks=doc_chunks,
                )
            )
        return results

    async def _search_documents_vector(self, query: str, k: int, abac_filter=None) -> list[DocumentSearchResult]:
        chunks = await self.rag_manager.retrieve(query=query, k=k, resource_types=[RAGSourceType.DOCUMENT.value])
        if not chunks:
            return []

        # Collect unique doc_ids from chunks
        doc_ids = {c.metadata.get(META_RESOURCE_ID) for c in chunks if c.metadata.get(META_RESOURCE_ID)}
        if not doc_ids:
            return []

        # Fetch Document DB models (provides filename + ABAC post-filter in one query)
        stmt = select(DocumentModel).where(
            DocumentModel.tenant_id == self.tenant_id,
            DocumentModel.id.in_(doc_ids),
        )
        if abac_filter is not None:
            stmt = stmt.where(abac_filter)
        result = await self.session.execute(stmt)
        doc_models = {d.id: d for d in result.scalars().all()}

        docs_map: dict[int, DocumentSearchResult] = {}
        for chunk in chunks:
            doc_id = chunk.metadata.get(META_RESOURCE_ID)
            if doc_id not in doc_models:
                continue
            if doc_id not in docs_map:
                docs_map[doc_id] = DocumentSearchResult(
                    doc_id=doc_id,
                    collection_id=doc_models[doc_id].collection_id,
                    filename=doc_models[doc_id].filename,
                    chunks=[],
                    source="vector",
                )
            docs_map[doc_id].chunks.append(_document_chunk_from_vector(chunk))
        return list(docs_map.values())

    async def _search_documents_hybrid(
        self,
        fts_query: str,
        vector_query: str,
        k: int,
        *,
        index_abac_filter=None,
        document_abac_filter=None,
        fts_weight: float = 0.4,
        vector_weight: float = 0.6,
    ) -> list[DocumentSearchResult]:
        fetch_k = k * 2
        fts_results = await self._search_documents_fts(fts_query, fetch_k, index_abac_filter)
        try:
            vector_results = await self._search_documents_vector(vector_query, fetch_k, document_abac_filter)
        except Exception as e:
            logger.warning("Vector search failed, falling back to FTS-only results: %s", e)
            return fts_results[:k]
        return self._merge_document_results_rrf(fts_results, vector_results, fts_weight, vector_weight)[:k]

    async def _get_relevant_chunks_for_doc(self, resource_id: int, query: str, k: int = 3) -> list[DocumentChunk]:
        all_chunks = await self.rag_manager.get_chunks_by_resource(
            resource_type="document",
            resource_id=resource_id,
            limit=100,
        )
        if not all_chunks:
            return []
        query_terms = set(query.lower().split())

        def score(chunk: Document) -> float:
            content_lower = chunk.page_content.lower()
            matches = sum(1 for term in query_terms if term in content_lower)
            return matches / len(query_terms) if query_terms else 0

        ranked = sorted(all_chunks, key=score, reverse=True)
        return [_document_chunk_from_vector(c, relevance=score(c)) for c in ranked[:k]]

    async def _authorize_resource_context(
        self,
        *,
        resource_type: SearchableResourceType,
        resource_id: int,
    ) -> None:
        if resource_type == RESOURCE_TYPE_DOCUMENT and self.user_id is not None:
            actor = ActorContext(tenant_id=self.tenant_id, user_id=self.user_id, user_role=self.user_role)
            collection_service = DocumentCollectionService(self.tenant_id, self.session)
            collection_id = await collection_service.require_document_access(
                document_id=resource_id,
                actor=actor,
                action=ABAC_ACTION_READ,
                delegated_ids=self._delegated_ids(getattr(self, "allowed_collection_ids", None)),
            )
            if self.allowed_collection_ids is not None and collection_id not in self.allowed_collection_ids:
                raise ResourceNotFoundError(f"Document {resource_id} not found")
        if resource_type == RESOURCE_TYPE_ASSET and self.user_id is not None:
            actor = ActorContext(tenant_id=self.tenant_id, user_id=self.user_id, user_role=self.user_role)
            data_source_service = DataSourceService(
                tenant_id=self.tenant_id,
                data_source_repo=DataSourceRepository(self.session),
                asset_repo=AssetMetadataRepository(self.session),
            )
            data_source_id = await data_source_service.require_asset_access(
                asset_id=resource_id,
                actor=actor,
                action=ABAC_ACTION_READ,
                delegated_ids=self._delegated_ids(getattr(self, "allowed_data_source_ids", None)),
            )
            if (
                getattr(self, "allowed_data_source_ids", None) is not None
                and data_source_id not in self.allowed_data_source_ids
            ):
                raise ResourceNotFoundError(f"Asset {resource_id} not found")

    @staticmethod
    def _normalize_context_anchors(chunk_indexes: list[int]) -> list[int]:
        anchors: list[int] = []
        seen: set[int] = set()
        for chunk_index in chunk_indexes:
            if chunk_index < 0:
                raise ValidationError(
                    "chunk_index must be >= 0",
                    details={"code": "INVALID_CHUNK_INDEX"},
                )
            if chunk_index in seen:
                continue
            seen.add(chunk_index)
            anchors.append(chunk_index)
            if len(anchors) >= MAX_DOCUMENT_CONTEXT_ANCHORS:
                break
        return anchors

    async def _fetch_context_docs(
        self,
        *,
        resource_type: SearchableResourceType,
        resource_id: int,
        chunk_index: int,
        context_range: int,
    ) -> list[Document]:
        if context_range < 0:
            raise ValidationError(
                "context_range must be >= 0",
                details={"code": "INVALID_CONTEXT_RANGE"},
            )
        index_docs = await self.rag_manager.get_context_chunks_by_resource(
            resource_type=resource_type,
            resource_id=resource_id,
            chunk_index=chunk_index,
            context_range=context_range,
        )
        anchor_page = next(
            (
                metadata.get("page")
                for doc in index_docs
                if (metadata := _chunk_metadata(doc)).get("chunk_index") == chunk_index
                and isinstance(metadata.get("page"), int)
            ),
            None,
        )
        if anchor_page is None:
            return index_docs

        page_docs = await self.rag_manager.get_chunks_by_page(
            resource_type=resource_type,
            resource_id=resource_id,
            page=anchor_page,
            limit=MAX_PAGE_CONTEXT_CHUNKS,
        )
        merged: dict[int, Document] = {}
        for doc in [*index_docs, *page_docs]:
            chunk_idx = _chunk_metadata(doc).get("chunk_index")
            if isinstance(chunk_idx, int) and chunk_idx not in merged:
                merged[chunk_idx] = doc
        return [merged[idx] for idx in sorted(merged)]

    async def get_resource_context_chunks(
        self,
        *,
        resource_type: SearchableResourceType,
        resource_id: int,
        chunk_index: int,
        context_range: int = 2,
    ) -> list[ResourceContextChunk]:
        if chunk_index is not None and chunk_index < 0:
            raise ValidationError(
                "chunk_index must be >= 0",
                details={"code": "INVALID_CHUNK_INDEX"},
            )
        await self._authorize_resource_context(resource_type=resource_type, resource_id=resource_id)
        context_docs = await self._fetch_context_docs(
            resource_type=resource_type,
            resource_id=resource_id,
            chunk_index=chunk_index,
            context_range=context_range,
        )
        if not context_docs:
            raise ResourceNotFoundError(
                "No context chunks found",
                details={
                    "code": "ANCHOR_CHUNK_NOT_FOUND",
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                },
            )
        chunks = [_context_chunk(document) for document in context_docs]
        if resource_type == RESOURCE_TYPE_DOCUMENT:
            return finalize_document_context_chunks(chunks, resource_id)
        return chunks

    async def get_resource_context_chunks_for_anchors(
        self,
        *,
        resource_type: SearchableResourceType,
        resource_id: int,
        chunk_indexes: list[int],
        context_range: int = 2,
    ) -> list[ResourceContextChunk]:
        anchors = self._normalize_context_anchors(chunk_indexes)
        if not anchors:
            raise ValidationError(
                "chunk_indexes must include at least one anchor",
                details={"code": "INVALID_CHUNK_INDEX"},
            )

        await self._authorize_resource_context(resource_type=resource_type, resource_id=resource_id)

        merged: dict[int, ResourceContextChunk] = {}
        for anchor in anchors:
            context_docs = await self._fetch_context_docs(
                resource_type=resource_type,
                resource_id=resource_id,
                chunk_index=anchor,
                context_range=context_range,
            )
            for doc in context_docs:
                chunk_idx = doc.metadata.get("chunk_index")
                if chunk_idx is None or chunk_idx in merged:
                    continue
                merged[chunk_idx] = _context_chunk(doc)

        if not merged:
            raise ResourceNotFoundError(
                "No context chunks found",
                details={
                    "code": "ANCHOR_CHUNK_NOT_FOUND",
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                },
            )

        chunks = [merged[idx] for idx in sorted(merged)]
        if resource_type == RESOURCE_TYPE_DOCUMENT:
            return finalize_document_context_chunks(chunks, resource_id)
        return chunks

    # ==================== Asset Search ====================

    async def search_assets(
        self, query: str, page: int = 1, page_size: int = 10
    ) -> tuple[list[SearchResultItem], PaginationRequest]:
        raw_query = (query or "").strip()
        logger.info("Searching assets: query='%s...', page=%s, page_size=%s", raw_query[:50], page, page_size)
        access_scope = await self._get_asset_access_scope()
        if access_scope is not None and access_scope.deny_all:
            return [], PaginationRequest.with_total(page=page, page_size=page_size, total=0)
        params = PaginationRequest(page=page, page_size=page_size)
        start, end = params.offset, params.end
        fetch_end = end + 1
        fts_query, vector_query = prepare_search_queries(raw_query)
        index_filter = access_scope.index_parent_filter if access_scope else None
        asset_filter = access_scope.asset_filter if access_scope else None
        merged = await self._search_assets_hybrid(
            fts_query,
            vector_query,
            fetch_end,
            index_abac_filter=index_filter,
            asset_abac_filter=asset_filter,
        )
        page_items = merged[start:end]
        has_next = len(merged) > end
        total = (end + 1) if has_next else (start + len(page_items))
        return [self._asset_to_item(a) for a in page_items], PaginationRequest.with_total(
            page=page, page_size=page_size, total=total
        )

    async def _search_assets_fts(self, query: str, k: int, index_abac_filter=None) -> list[AssetSearchResult]:
        """FTS search for assets via ResourceIndex with data-source authz pushdown."""
        ri_rows = await self.resource_index_repo.search_assets_fts(
            tenant_id=self.tenant_id, query=query, limit=k, abac_filter=index_abac_filter
        )
        if not ri_rows:
            return []

        asset_ids = [ri.resource_id for ri, _, *_ in ri_rows]
        rank_map = {ri.resource_id: float(rank or 0) for ri, rank, *_ in ri_rows}

        assets = await self.asset_repo.list_by_ids(asset_ids, self.tenant_id)
        ds_ids = {a.data_source_id for a in assets if a.data_source_id}
        ds_map = {s.id: s for s in await self.data_source_repo.list_by_ids(list(ds_ids), self.tenant_id)}
        asset_map = {a.id: a for a in assets}

        results = []
        for ri, _, _ in ri_rows:
            asset = asset_map.get(ri.resource_id)
            if asset is None:
                continue
            ad = db_asset_metadata_to_domain(asset)
            ds = ds_map.get(ad.data_source_id)
            results.append(
                AssetSearchResult(
                    asset_id=ad.id,
                    data_source_id=ad.data_source_id,
                    data_source_name=ds.name if ds else "",
                    data_source_type=ds.type if ds else "",
                    asset_name=ad.asset_name,
                    asset_type=ad.asset_type,
                    resolved_description=ad.resolved_description(),
                    columns=ad.resolved_columns(),
                    row_count=ad.row_count,
                    rrf_score=rank_map.get(ad.id, 0),
                    source="fts",
                )
            )
        return results

    async def _search_assets_vector(self, query: str, k: int, asset_abac_filter=None) -> list[AssetSearchResult]:
        chunks = await self.rag_manager.retrieve(query=query, k=k, resource_types=[RAGSourceType.ASSET.value])
        if not chunks:
            return []

        asset_ids = [
            aid for aid in {c.metadata.get(META_RESOURCE_ID) for c in chunks} if isinstance(aid, int) and aid > 0
        ]
        if not asset_ids:
            return []

        assets = await self.asset_repo.list_by_ids(asset_ids, self.tenant_id, abac_filter=asset_abac_filter)
        ds_ids = {a.data_source_id for a in assets if a.data_source_id}
        ds_map = {s.id: s for s in await self.data_source_repo.list_by_ids(list(ds_ids), self.tenant_id)}

        results = []
        for a in assets:
            ad = db_asset_metadata_to_domain(a)
            ds = ds_map.get(ad.data_source_id)
            results.append(
                AssetSearchResult(
                    asset_id=ad.id,
                    data_source_id=ad.data_source_id,
                    data_source_name=ds.name if ds else "",
                    data_source_type=ds.type if ds else "",
                    asset_name=ad.asset_name,
                    asset_type=ad.asset_type,
                    resolved_description=ad.resolved_description(),
                    columns=ad.resolved_columns(),
                    row_count=ad.row_count,
                    source="vector",
                )
            )
        return results

    async def _search_assets_hybrid(
        self,
        fts_query: str,
        vector_query: str,
        k: int,
        *,
        index_abac_filter=None,
        asset_abac_filter=None,
        fts_weight: float = 0.5,
        vector_weight: float = 0.5,
    ) -> list[AssetSearchResult]:
        fetch_k = k * 2
        fts = await self._search_assets_fts(fts_query, fetch_k, index_abac_filter)
        vec = await self._search_assets_vector(vector_query, fetch_k, asset_abac_filter)
        return self._merge_asset_results_rrf(fts, vec, fts_weight, vector_weight)[:k]

    # ==================== API Connector Search ====================

    async def search_api_connectors(
        self, query: str, page: int = 1, page_size: int = 10
    ) -> tuple[list[SearchResultItem], PaginationRequest]:
        raw_query = (query or "").strip()
        logger.info("Searching api connectors: query='%s...', page=%s, page_size=%s", raw_query[:50], page, page_size)
        authz_filter = await self._get_api_connector_authz_filter()
        if authz_filter is not None and authz_filter.deny_all:
            return [], PaginationRequest.with_total(page=page, page_size=page_size, total=0)
        scoped_ids = await self._resolve_api_connector_scope_ids(authz_filter)
        if scoped_ids == []:
            return [], PaginationRequest.with_total(page=page, page_size=page_size, total=0)
        params = PaginationRequest(page=page, page_size=page_size)
        start, end = params.offset, params.end
        fetch_end = end + 1
        fts_query, vector_query = prepare_search_queries(raw_query)
        merged = await self._search_api_connectors_hybrid(
            fts_query=fts_query,
            vector_query=vector_query,
            k=fetch_end,
            scoped_connector_ids=scoped_ids,
            authz_filter=authz_filter,
        )
        page_items = merged[start:end]
        has_next = len(merged) > end
        total = (end + 1) if has_next else (start + len(page_items))
        return [self._api_connector_to_item(i) for i in page_items], PaginationRequest.with_total(
            page=page, page_size=page_size, total=total
        )

    async def _search_api_connectors_fts(
        self,
        query: str,
        k: int,
        scoped_connector_ids: list[int] | None,
        authz_filter=None,
    ) -> list[ApiConnectorSearchResult]:
        """FTS search for API connector operations via ResourceIndex."""
        ri_rows = await self.resource_index_repo.search_api_operations_fts(
            tenant_id=self.tenant_id,
            query=query,
            limit=k,
            abac_filter=authz_filter.clause if authz_filter is not None and not authz_filter.allow_all else None,
            parent_ids=scoped_connector_ids,
        )
        if not ri_rows:
            return []

        op_ids = [ri.resource_id for ri, _, *_ in ri_rows]
        rank_map = {ri.resource_id: float(rank or 0) for ri, rank, *_ in ri_rows}

        rows = await self.api_operation_repo.list_active_by_ids(
            tenant_id=self.tenant_id,
            operation_ids=op_ids,
            scoped_connector_ids=scoped_connector_ids,
            limit=k,
        )
        if not rows:
            return []

        conn_ids = sorted({r.connector_id for r in rows})
        conns = await self.api_connector_repo.get_by_ids_and_tenant(
            conn_ids,
            self.tenant_id,
            authz_filter.clause if authz_filter is not None and not authz_filter.allow_all else None,
        )
        conn_map = {c.id: c.name for c in conns}

        results = []
        for r in rows:
            if r.connector_id not in conn_map:
                continue
            results.append(
                ApiConnectorSearchResult(
                    operation_uid=r.operation_uid,
                    connector_id=r.connector_id,
                    connector_name=conn_map.get(r.connector_id),
                    method=r.method,
                    path_template=r.path_template,
                    operation_id=r.id,
                    summary=r.summary or "",
                    description=r.description,
                    tags=r.tags or [],
                    rrf_score=rank_map.get(r.id, 0),
                    source="fts",
                )
            )
        return results

    async def _search_api_connectors_vector(
        self,
        query: str,
        k: int,
        scoped_connector_ids: list[int] | None,
        authz_filter=None,
    ) -> list[ApiConnectorSearchResult]:
        """Vector search for API connector operations via RAG."""
        chunks = await self.rag_manager.retrieve(
            query=query,
            k=k,
            resource_types=[RAGSourceType.API_CONNECTOR.value],
        )
        if not chunks:
            return []

        op_ids = [rid for rid in {c.metadata.get("resource_id") for c in chunks} if isinstance(rid, int) and rid > 0]
        if not op_ids:
            return []

        rows = await self.api_operation_repo.list_active_by_ids(
            tenant_id=self.tenant_id,
            operation_ids=op_ids,
            scoped_connector_ids=scoped_connector_ids,
            limit=k,
        )
        if not rows:
            return []

        conn_ids = sorted({r.connector_id for r in rows})
        conns = await self.api_connector_repo.get_by_ids_and_tenant(
            conn_ids,
            self.tenant_id,
            authz_filter.clause if authz_filter is not None and not authz_filter.allow_all else None,
        )
        conn_map = {c.id: c.name for c in conns}

        results = []
        for r in rows:
            if r.connector_id not in conn_map:
                continue
            results.append(
                ApiConnectorSearchResult(
                    operation_uid=r.operation_uid,
                    connector_id=r.connector_id,
                    connector_name=conn_map.get(r.connector_id),
                    method=r.method,
                    path_template=r.path_template,
                    operation_id=r.id,
                    summary=r.summary or "",
                    description=r.description,
                    tags=r.tags or [],
                    source="vector",
                )
            )
        return results

    async def _search_api_connectors_hybrid(
        self,
        fts_query: str,
        vector_query: str,
        k: int,
        scoped_connector_ids: list[int] | None,
        authz_filter=None,
        fts_weight: float = 0.5,
        vector_weight: float = 0.5,
    ) -> list[ApiConnectorSearchResult]:
        fetch_k = k * 2
        fts_results = await self._search_api_connectors_fts(fts_query, fetch_k, scoped_connector_ids, authz_filter)
        try:
            vector_results = await self._search_api_connectors_vector(
                vector_query, fetch_k, scoped_connector_ids, authz_filter
            )
        except Exception as e:
            logger.warning("Vector search failed, falling back to FTS-only results: %s", e)
            return fts_results[:k]
        return self._merge_api_connector_results_rrf(fts_results, vector_results, fts_weight, vector_weight)[:k]

    def _merge_api_connector_results_rrf(
        self,
        fts: list[ApiConnectorSearchResult],
        vec: list[ApiConnectorSearchResult],
        fw: float,
        vw: float,
        k: int = 60,
    ) -> list[ApiConnectorSearchResult]:
        entries = self._merge_ranked_results_rrf(
            fts_items=fts,
            vector_items=vec,
            key_fn=lambda r: r.operation_uid,
            fts_weight=fw,
            vector_weight=vw,
            k=k,
        )
        results = []
        for item in entries:
            result = item["fts_item"] or item["vector_item"]
            if result is None:
                continue
            result.rrf_score = item["score"]
            result.source = item["source"]
            results.append(result)
        return results

    @staticmethod
    def _merge_ranked_results_rrf(
        *, fts_items, vector_items, key_fn, fts_weight: float, vector_weight: float, k: int = 60
    ) -> list[dict[str, Any]]:
        merged: dict[Any, dict[str, Any]] = {}
        for rank, item in enumerate(fts_items, 1):
            key = key_fn(item)
            merged[key] = {
                "key": key,
                "fts_item": item,
                "vector_item": None,
                "score": fts_weight / (k + rank),
                "source": "fts",
            }
        for rank, item in enumerate(vector_items, 1):
            key = key_fn(item)
            score = vector_weight / (k + rank)
            existing = merged.get(key)
            if existing is None:
                merged[key] = {"key": key, "fts_item": None, "vector_item": item, "score": score, "source": "vector"}
            else:
                existing["vector_item"] = item
                existing["score"] += score
                existing["source"] = "hybrid"
        return sorted(merged.values(), key=lambda i: i["score"], reverse=True)

    def _merge_document_results_rrf(
        self, fts: list[DocumentSearchResult], vec: list[DocumentSearchResult], fw: float, vw: float, k: int = 60
    ) -> list[DocumentSearchResult]:
        entries = self._merge_ranked_results_rrf(
            fts_items=fts, vector_items=vec, key_fn=lambda r: r.doc_id, fts_weight=fw, vector_weight=vw, k=k
        )
        results = []
        for item in entries:
            fi, vi = item["fts_item"], item["vector_item"]
            result = fi or vi
            if result is None:
                continue
            result.rrf_score = item["score"]
            result.source = item["source"]
            if fi is not None and vi is not None:
                existing = {c.chunk_index for c in fi.chunks}
                for c in vi.chunks:
                    if c.chunk_index not in existing:
                        fi.chunks.append(c)
            results.append(result)
        return results

    def _merge_asset_results_rrf(
        self, fts: list[AssetSearchResult], vec: list[AssetSearchResult], fw: float, vw: float, k: int = 60
    ) -> list[AssetSearchResult]:
        entries = self._merge_ranked_results_rrf(
            fts_items=fts, vector_items=vec, key_fn=lambda r: r.asset_id, fts_weight=fw, vector_weight=vw, k=k
        )
        results = []
        for item in entries:
            result = item["fts_item"] or item["vector_item"]
            if result is None:
                continue
            result.rrf_score = item["score"]
            result.source = item["source"]
            results.append(result)
        return results

    async def _get_document_access_scope(self) -> DocumentAccessScope | None:
        if self.user_id is None:
            return None
        actor = ActorContext(tenant_id=self.tenant_id, user_id=self.user_id, user_role=self.user_role)
        collection_service = DocumentCollectionService(self.tenant_id, self.session)
        scope = await collection_service.build_document_access_scope(
            actor=actor,
            action=ABAC_ACTION_READ,
        )
        allowed_ids = await self._scoped_allowed_ids(RESOURCE_TYPE_DOCUMENT_COLLECTION, self.allowed_collection_ids)
        return self._clip_collection_scope(scope, allowed_ids)

    def _clip_collection_scope(
        self, scope: DocumentAccessScope, allowed_ids: list[int] | None = None
    ) -> DocumentAccessScope:
        """Restrict document search to the agent's attached collections.

        With ``delegate``, attached collections are readable in this chat even
        if the user has no collection ACL. Without it, user ACL ∩ agent set.
        """
        if allowed_ids is None and self.allowed_collection_ids is None:
            return scope
        delegate = getattr(self, "delegate", False)
        user_filter = AuthzSqlFilter(
            allow_all=scope.allow_all,
            deny_all=scope.deny_all,
            clause=scope.document_filter,
        )
        combined = combine_agent_scope(
            user_scope=user_filter,
            id_column=DocumentModel.collection_id,
            allowed_ids=allowed_ids,
            delegate=delegate,
        )
        index_combined = combine_agent_scope(
            user_scope=AuthzSqlFilter(
                allow_all=scope.allow_all,
                deny_all=scope.deny_all,
                clause=scope.index_parent_filter,
            ),
            id_column=ResourceIndex.parent_id,
            allowed_ids=allowed_ids,
            delegate=delegate,
        )
        return DocumentAccessScope(
            deny_all=combined.deny_all,
            allow_all=combined.allow_all,
            document_filter=combined.clause,
            index_parent_filter=index_combined.clause,
        )

    async def _get_document_authz_filter(self):
        access_scope = await self._get_document_access_scope()
        if access_scope is None:
            return None
        if access_scope.deny_all:
            return AuthzSqlFilter(allow_all=False, deny_all=True, clause=None)
        if access_scope.allow_all:
            return AuthzSqlFilter(allow_all=True, deny_all=False, clause=None)
        return AuthzSqlFilter(allow_all=False, deny_all=False, clause=access_scope.document_filter)

    async def _get_asset_access_scope(self) -> AssetAccessScope | None:
        if self.user_id is None:
            return None
        actor = ActorContext(tenant_id=self.tenant_id, user_id=self.user_id, user_role=self.user_role)
        data_source_service = DataSourceService(
            tenant_id=self.tenant_id,
            data_source_repo=self.data_source_repo,
            asset_repo=self.asset_repo,
        )
        scope = await data_source_service.build_asset_access_scope(
            actor=actor,
            action=ABAC_ACTION_READ,
        )
        allowed_ids = await self._scoped_allowed_ids(RESOURCE_TYPE_DATA_SOURCE, self.allowed_data_source_ids)
        if allowed_ids is None and self.allowed_data_source_ids is None:
            return scope
        user_filter = AuthzSqlFilter(
            allow_all=scope.allow_all,
            deny_all=scope.deny_all,
            clause=scope.asset_filter,
        )
        combined = combine_agent_scope(
            user_scope=user_filter,
            id_column=AssetMetadata.data_source_id,
            allowed_ids=allowed_ids,
            delegate=getattr(self, "delegate", False),
        )
        index_combined = combine_agent_scope(
            user_scope=AuthzSqlFilter(
                allow_all=scope.allow_all,
                deny_all=scope.deny_all,
                clause=scope.index_parent_filter,
            ),
            id_column=ResourceIndex.parent_id,
            allowed_ids=allowed_ids,
            delegate=getattr(self, "delegate", False),
        )
        return AssetAccessScope(
            deny_all=combined.deny_all,
            allow_all=combined.allow_all,
            asset_filter=combined.clause,
            index_parent_filter=index_combined.clause,
        )

    async def _get_api_connector_authz_filter(self):
        if self.user_id is None:
            return None
        user_scope = await build_unified_resource_filter(
            db_session=self.session,
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            user_role=self.user_role,
            resource_type=RESOURCE_TYPE_API_CONNECTOR,
            resource_model=ApiConnector,
        )
        allowed_ids = await self._scoped_allowed_ids(RESOURCE_TYPE_API_CONNECTOR, self.allowed_api_connector_ids)
        return combine_agent_scope(
            user_scope=user_scope,
            id_column=ApiConnector.id,
            allowed_ids=allowed_ids,
            delegate=getattr(self, "delegate", False),
        )

    def _delegated_ids(self, allowed_ids: list[int] | None) -> list[int] | None:
        if not getattr(self, "delegate", False) or not allowed_ids:
            return None
        return list(allowed_ids)

    async def _scoped_allowed_ids(self, resource_type, allowed_ids: list[int] | None) -> list[int] | None:
        if allowed_ids is None:
            return None
        if not getattr(self, "delegate", False) or self.user_id is None:
            return allowed_ids
        return await filter_explicit_deny_ids(
            self.session,
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            user_role=self.user_role,
            resource_type=resource_type,
            resource_ids=allowed_ids,
        )

    async def _filter_connector_ids(self, authz_filter_clause) -> list[int]:
        stmt = select(ApiConnector.id).where(ApiConnector.tenant_id == self.tenant_id, authz_filter_clause)
        result = await self.session.execute(stmt)
        return [r[0] for r in result.all()]

    async def _resolve_api_connector_scope_ids(self, authz_filter) -> list[int] | None:
        if authz_filter is None or authz_filter.allow_all:
            return None
        return await self._filter_connector_ids(authz_filter.clause)
