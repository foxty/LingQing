"""Parser registry for document processing engines."""

from __future__ import annotations

from apps.config import EnvConfig
from apps.shared.document.parsers.base import DocumentParserPort
from apps.shared.document.parsers.docling import DoclingDocumentParser
from apps.shared.document.parsers.mineru import MinerUDocumentParser
from apps.shared.document.types import DocumentParserKey, normalize_document_parser_name
from apps.shared.infra.storage import FileStorage


class DocumentParserRegistry:
    def __init__(self, file_storage: FileStorage):
        self._file_storage = file_storage
        self._parsers: dict[str, DocumentParserPort] = {
            DocumentParserKey.MINERU.value: MinerUDocumentParser(file_storage),
            DocumentParserKey.DOCLING.value: DoclingDocumentParser(file_storage),
        }

    def get(self, parser_name: str | None = None) -> DocumentParserPort:
        resolved = normalize_document_parser_name(parser_name, configured=EnvConfig.DOCUMENT_PARSER)
        parser = self._parsers.get(resolved)
        if parser is None:
            raise ValueError(f"Unsupported document parser: {resolved}")
        return parser

    def configured_parser_name(self) -> str:
        return normalize_document_parser_name(None, configured=EnvConfig.DOCUMENT_PARSER)


def get_parser_registry(file_storage: FileStorage) -> DocumentParserRegistry:
    return DocumentParserRegistry(file_storage)
