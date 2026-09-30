"""Tests for document on-disk layout helpers."""

from __future__ import annotations

import pytest

from apps.shared.document.manifest import (
    document_original_relative_key,
    is_document_original_storage_key,
    normalize_document_filename,
)


def test_document_original_relative_key_uses_document_id_and_basename():
    assert document_original_relative_key(42, "report.pdf") == "42/original/report.pdf"


def test_document_original_relative_key_flattens_path_like_names():
    assert document_original_relative_key(42, r"nested\report.pdf") == "42/original/nested - report.pdf"
    assert document_original_relative_key(42, "nested/report.pdf") == "42/original/nested - report.pdf"
    assert document_original_relative_key(42, "../report.pdf") == "42/original/.. - report.pdf"


def test_normalize_document_filename_flattens_gemini_note_paths():
    raw = "CMS Search & DLP Knowledge Sharing Session - 2026/09/01 11:01 CST - Notes by Gemini.docx"
    expected = "CMS Search & DLP Knowledge Sharing Session - 2026 - 09 - 01 11:01 CST - Notes by Gemini.docx"
    assert normalize_document_filename(raw) == expected
    assert document_original_relative_key(7, raw) == f"7/original/{expected}"


def test_document_original_relative_key_rejects_unsafe_names():
    with pytest.raises(ValueError):
        document_original_relative_key(42, "")
    with pytest.raises(ValueError):
        document_original_relative_key(42, "..")


@pytest.mark.parametrize(
    ("document_id", "storage_key", "expected"),
    [
        (42, "42/original/report.pdf", True),
        (42, "report.pdf", False),
        (42, "43/original/report.pdf", False),
        (42, "s3://bucket/42/original/report.pdf", False),
    ],
)
def test_is_document_original_storage_key(document_id: int, storage_key: str, expected: bool):
    assert is_document_original_storage_key(document_id, storage_key) is expected
