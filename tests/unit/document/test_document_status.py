"""Tests for document status enum."""

from apps.shared.document.types import DocumentStatus, coerce_document_status, document_status_value


def test_document_status_roundtrip():
    assert document_status_value(DocumentStatus.ACTIVE) == "active"
    assert coerce_document_status("processing") == DocumentStatus.PROCESSING
