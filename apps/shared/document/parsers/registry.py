"""Parser registry for document processing engines."""

from __future__ import annotations

from apps.config import EnvConfig
from apps.shared.document.parsers.base import DocumentParserPort
from apps.shared.document.parsers.default import DefaultDocumentParser
from apps.shared.document.parsers.docling import DoclingDocumentParser
from apps.shared.document.parsers.mineru import MinerUDocumentParser
from apps.shared.infra.storage import FileStorage


class DocumentParserRegistry:
    def __init__(self, file_storage: FileStorage):
        self._file_storage = file_storage
        self._parsers: dict[str, DocumentParserPort] = {
            "default": DefaultDocumentParser(file_storage),
            "mineru": MinerUDocumentParser(file_storage),
            "docling": DoclingDocumentParser(file_storage),
        }

    def get(self, parser_name: str | None = None) -> DocumentParserPort:
        resolved = (parser_name or EnvConfig.DOCUMENT_PARSER or "default").strip().lower()
        parser = self._parsers.get(resolved)
        if parser is None:
            raise ValueError(f"Unsupported document parser: {resolved}")
        return parser

    def configured_parser_name(self) -> str:
        return (EnvConfig.DOCUMENT_PARSER or "default").strip().lower()


def get_parser_registry(file_storage: FileStorage) -> DocumentParserRegistry:
    return DocumentParserRegistry(file_storage)
