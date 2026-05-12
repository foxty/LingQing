"""Tests for document parser registry."""

import pytest

from apps.config import EnvConfig
from apps.shared.document.parsers.docling import DoclingDocumentParser
from apps.shared.document.parsers.default import DefaultDocumentParser
from apps.shared.document.parsers.mineru import MinerUDocumentParser
from apps.shared.document.parsers.registry import DocumentParserRegistry, get_parser_registry


class _FakeStorage:
    async def read(self, file_url: str) -> bytes:
        return b""


def test_registry_resolves_default_parser():
    registry = DocumentParserRegistry(_FakeStorage())
    parser = registry.get("default")
    assert isinstance(parser, DefaultDocumentParser)
    assert parser.name == "default"


def test_registry_resolves_docling_parser():
    registry = DocumentParserRegistry(_FakeStorage())
    parser = registry.get("docling")
    assert isinstance(parser, DoclingDocumentParser)
    assert parser.name == "docling"


def test_registry_resolves_mineru_parser():
    registry = DocumentParserRegistry(_FakeStorage())
    parser = registry.get("mineru")
    assert isinstance(parser, MinerUDocumentParser)
    assert parser.name == "mineru"


def test_registry_uses_document_parser_env(monkeypatch):
    monkeypatch.setattr(EnvConfig, "DOCUMENT_PARSER", "docling")
    registry = DocumentParserRegistry(_FakeStorage())
    assert registry.configured_parser_name() == "docling"
    assert registry.get().name == "docling"


def test_registry_unknown_parser_raises():
    registry = DocumentParserRegistry(_FakeStorage())
    with pytest.raises(ValueError, match="Unsupported document parser: unknown"):
        registry.get("unknown")


def test_get_parser_registry_factory():
    storage = _FakeStorage()
    registry = get_parser_registry(storage)
    assert registry.get("default").name == "default"
