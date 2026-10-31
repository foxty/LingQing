"""Tests for document parser registry."""

import pytest

from apps.config import EnvConfig
from apps.shared.document.parsers.docling import DoclingDocumentParser
from apps.shared.document.parsers.mineru import MinerUDocumentParser
from apps.shared.document.parsers.registry import DocumentParserRegistry, get_parser_registry
from apps.shared.document.types import (
    DEFAULT_DOCUMENT_PARSER,
    DocumentParserKey,
    LEGACY_SOURCE_PARSER_DEFAULT,
    normalize_document_parser_name,
)


class _FakeStorage:
    async def read(self, file_url: str) -> bytes:
        return b""


def test_normalize_document_parser_name_legacy_alias():
    assert normalize_document_parser_name(LEGACY_SOURCE_PARSER_DEFAULT) == DocumentParserKey.DOCLING


def test_normalize_document_parser_name_falls_back_to_configured():
    assert normalize_document_parser_name(None, configured=DocumentParserKey.MINERU) == DocumentParserKey.MINERU


def test_registry_resolves_legacy_default_alias_to_docling():
    registry = DocumentParserRegistry(_FakeStorage())
    parser = registry.get(LEGACY_SOURCE_PARSER_DEFAULT)
    assert isinstance(parser, DoclingDocumentParser)
    assert parser.name == DocumentParserKey.DOCLING


def test_registry_resolves_docling_parser():
    registry = DocumentParserRegistry(_FakeStorage())
    parser = registry.get(DocumentParserKey.DOCLING)
    assert isinstance(parser, DoclingDocumentParser)
    assert parser.name == DocumentParserKey.DOCLING


def test_registry_resolves_mineru_parser():
    registry = DocumentParserRegistry(_FakeStorage())
    parser = registry.get(DocumentParserKey.MINERU)
    assert isinstance(parser, MinerUDocumentParser)
    assert parser.name == DocumentParserKey.MINERU


def test_registry_uses_document_parser_env(monkeypatch):
    monkeypatch.setattr(EnvConfig, "DOCUMENT_PARSER", DocumentParserKey.MINERU)
    registry = DocumentParserRegistry(_FakeStorage())
    assert registry.configured_parser_name() == DocumentParserKey.MINERU
    assert registry.get().name == DocumentParserKey.MINERU


def test_registry_default_env_is_docling(monkeypatch):
    monkeypatch.delenv("DOCUMENT_PARSER", raising=False)
    monkeypatch.setattr(EnvConfig, "DOCUMENT_PARSER", DEFAULT_DOCUMENT_PARSER)
    registry = DocumentParserRegistry(_FakeStorage())
    assert registry.configured_parser_name() == DEFAULT_DOCUMENT_PARSER
    assert registry.get().name == DocumentParserKey.DOCLING


def test_registry_unknown_parser_raises():
    registry = DocumentParserRegistry(_FakeStorage())
    with pytest.raises(ValueError, match="Unsupported document parser: unknown"):
        registry.get("unknown")


def test_get_parser_registry_factory():
    storage = _FakeStorage()
    registry = get_parser_registry(storage)
    assert registry.get(LEGACY_SOURCE_PARSER_DEFAULT).name == DocumentParserKey.DOCLING
