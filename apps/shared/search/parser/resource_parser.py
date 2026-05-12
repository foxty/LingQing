"""Resource-aware chunking for vector indexing."""

from __future__ import annotations

from typing import NotRequired, TypedDict

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

import apps.config
from apps.shared.document.chunking import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    segment_blocks,
)
from apps.shared.document.manifest import extract_text_from_blocks
from apps.shared.domain.types import (
    RESOURCE_TYPE_API_CONNECTOR,
    RESOURCE_TYPE_ASSET,
    RESOURCE_TYPE_DOCUMENT,
    SearchableResourceType,
)
from apps.shared.infra.storage import FileStorage
from apps.shared.search.parser.extraction import extract_text_from_raw
from apps.shared.search.parser.normalization import normalize_for_embedding
from apps.shared.search.parser.tokenization import unified_tokenize
from apps.shared.search.parser.types import ParseResult


class IndexedChunkMetadata(TypedDict):
    source_parser: str
    chunk_index: int
    block_type: str
    filename: NotRequired[str]
    page: NotRequired[int]
    image_uri: NotRequired[str]


class ResourceParser:
    """Factory for parsing different resource types."""

    DEFAULT_CHUNK_SIZE = DEFAULT_CHUNK_SIZE
    DEFAULT_CHUNK_OVERLAP = DEFAULT_CHUNK_OVERLAP

    def __init__(
        self,
        file_storage: FileStorage | None = None,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
        min_chars: int | None = None,
        table_max_chars: int | None = None,
    ):
        self.file_storage = file_storage
        env = apps.config.EnvConfig
        self._chunk_size = chunk_size if chunk_size is not None else env.DOCUMENT_CHUNK_SIZE
        self._chunk_overlap = chunk_overlap if chunk_overlap is not None else env.DOCUMENT_CHUNK_OVERLAP
        self._min_chars = min_chars if min_chars is not None else env.DOCUMENT_CHUNK_MIN_CHARS
        self._table_max_chars = table_max_chars if table_max_chars is not None else env.DOCUMENT_TABLE_MAX_CHARS
        self._text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self._chunk_size,
            chunk_overlap=self._chunk_overlap,
            separators=["\n\n", "\n", "。", "？", "！", " ", ""],
        )

    def from_raw(
        self,
        raw_content: dict,
        resource_type: SearchableResourceType,
        source_parser: str = "default",
        blocks_document: dict | None = None,
    ) -> ParseResult:
        if blocks_document is not None:
            text = extract_text_from_blocks(blocks_document)
        else:
            text = extract_text_from_raw(raw_content)
        tokenized_content = unified_tokenize(text)
        chunks = self._chunk_from_raw(
            raw_content,
            resource_type,
            source_parser,
            blocks_document=blocks_document,
        )
        return ParseResult(tokenized_content=tokenized_content, chunks=chunks)

    def _chunk_from_raw(
        self,
        raw_content: dict,
        resource_type: SearchableResourceType,
        source_parser: str = "default",
        blocks_document: dict | None = None,
    ) -> list[Document]:
        if resource_type == RESOURCE_TYPE_DOCUMENT:
            if blocks_document is not None:
                return self._chunk_blocks_document(blocks_document, raw_content, source_parser)
            return self._chunk_document(raw_content, source_parser)
        if resource_type == RESOURCE_TYPE_ASSET:
            return self._chunk_asset(raw_content)
        if resource_type == RESOURCE_TYPE_API_CONNECTOR:
            return self._chunk_api_connector(raw_content)

        text = extract_text_from_raw(raw_content)
        if not text:
            return []
        return [Document(page_content=normalize_for_embedding(text), metadata={})]

    def _chunk_document(self, raw_content: dict, source_parser: str = "default") -> list[Document]:
        filename = ""
        meta = raw_content.get("meta", {})
        if meta and isinstance(meta, dict):
            filename = meta.get("filename", "")

        text = raw_content.get("text")
        if not text or not str(text).strip():
            return []

        return self._chunk_single_document(text, filename=filename, source_parser=source_parser)

    def _chunk_blocks_document(
        self,
        blocks_document: dict,
        raw_content: dict,
        source_parser: str,
    ) -> list[Document]:
        filename = ""
        meta = raw_content.get("meta", {})
        if isinstance(meta, dict):
            filename = meta.get("filename", "")

        segments = segment_blocks(
            blocks_document,
            max_chars=self._chunk_size,
            overlap=self._chunk_overlap,
            min_chars=self._min_chars,
            table_max_chars=self._table_max_chars,
        )

        chunks: list[Document] = []
        for chunk_index, segment in enumerate(segments):
            normalized_text = normalize_for_embedding(segment.text)
            if not normalized_text:
                continue

            metadata: IndexedChunkMetadata = {
                "source_parser": source_parser,
                "chunk_index": chunk_index,
                "block_type": segment.block_types[-1] if len(segment.block_types) == 1 else segment.kind,
            }
            if filename:
                metadata["filename"] = filename
            if segment.page is not None:
                metadata["page"] = segment.page
            if segment.uri:
                metadata["image_uri"] = segment.uri

            chunks.append(Document(page_content=normalized_text, metadata=metadata))

        return chunks

    def _chunk_single_document(
        self,
        text: str,
        filename: str,
        source_parser: str,
    ) -> list[Document]:
        normalized_text = normalize_for_embedding(text)
        docs = self._text_splitter.create_documents([normalized_text])

        chunks = []
        for idx, doc in enumerate(docs):
            chunk_meta = {
                "source_parser": source_parser,
                "chunk_index": idx,
            }
            if filename:
                chunk_meta["filename"] = filename

            chunks.append(Document(page_content=doc.page_content, metadata=chunk_meta))

        return chunks

    def _chunk_asset(self, raw_content: dict) -> list[Document]:
        text = extract_text_from_raw(raw_content)
        if not text:
            return []

        meta = {}
        meta.update(raw_content.get("meta", {}))
        return [Document(page_content=normalize_for_embedding(text), metadata=meta)]

    def _chunk_api_connector(self, raw_content: dict) -> list[Document]:
        text = extract_text_from_raw(raw_content)
        if not text:
            return []

        meta = {}
        meta.update(raw_content.get("meta", {}))
        return [Document(page_content=normalize_for_embedding(text), metadata=meta)]
