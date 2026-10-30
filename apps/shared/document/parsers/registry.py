"""Parser registry for document processing engines."""

from __future__ import annotations

from apps.config import EnvConfig
from apps.shared.document.parsers.base import DocumentParserPort
from apps.shared.document.parsers.docling import DoclingDocumentParser
from apps.shared.document.parsers.mineru import MinerUDocumentParser
from apps.shared.infra.storage import FileStorage

# Historical rows and env may still say "default" (legacy in-process parser, removed).
_PARSER_ALIASES: dict[str, str] = {"default": "docling"}


def _normalize_parser_name(name: str | None) -> str:
    resolved = (name or EnvConfig.DOCUMENT_PARSER or "docling").strip().lower()
    return _PARSER_ALIASES.get(resolved, resolved)


class DocumentParserRegistry:
    def __init__(self, file_storage: FileStorage):
        self._file_storage = file_storage
        self._parsers: dict[str, DocumentParserPort] = {
            "mineru": MinerUDocumentParser(file_storage),
            "docling": DoclingDocumentParser(file_storage),
        }

    def get(self, parser_name: str | None = None) -> DocumentParserPort:
        resolved = _normalize_parser_name(parser_name)
        parser = self._parsers.get(resolved)
        if parser is None:
            raise ValueError(f"Unsupported document parser: {resolved}")
        return parser

    def configured_parser_name(self) -> str:
        return _normalize_parser_name(None)


def get_parser_registry(file_storage: FileStorage) -> DocumentParserRegistry:
    return DocumentParserRegistry(file_storage)
