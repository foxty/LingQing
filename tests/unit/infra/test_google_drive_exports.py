"""Tests for Google Drive export mime mappings."""

from __future__ import annotations

from datetime import UTC, datetime

from apps.shared.infra.external_files.google_drive import (
    EXPORT_EXTENSION_BY_MIME,
    GOOGLE_MIME_DOCUMENT,
    GOOGLE_MIME_PRESENTATION,
    GOOGLE_MIME_SPREADSHEET,
    GOOGLE_NATIVE_EXPORT_MIMES,
    _parse_drive_timestamp,
    export_filename,
    is_google_native_mime,
    is_supported_drive_file,
)


def test_google_native_export_mimes():
    assert GOOGLE_NATIVE_EXPORT_MIMES[GOOGLE_MIME_DOCUMENT] == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert GOOGLE_NATIVE_EXPORT_MIMES[GOOGLE_MIME_SPREADSHEET] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert GOOGLE_NATIVE_EXPORT_MIMES[GOOGLE_MIME_PRESENTATION] == (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )


def test_export_extension_mapping():
    assert EXPORT_EXTENSION_BY_MIME[GOOGLE_MIME_DOCUMENT] == ".docx"
    assert EXPORT_EXTENSION_BY_MIME[GOOGLE_MIME_SPREADSHEET] == ".xlsx"
    assert EXPORT_EXTENSION_BY_MIME[GOOGLE_MIME_PRESENTATION] == ".pptx"


def test_export_filename_for_google_native_types():
    assert export_filename("Quarterly Plan", GOOGLE_MIME_DOCUMENT) == "Quarterly Plan.docx"
    assert export_filename("Budget", GOOGLE_MIME_SPREADSHEET) == "Budget.xlsx"
    assert export_filename("All Hands", GOOGLE_MIME_PRESENTATION) == "All Hands.pptx"


def test_is_supported_drive_file():
    assert is_supported_drive_file("notes.pdf", "application/pdf") is True
    assert is_supported_drive_file("notes.docx", "application/octet-stream") is True
    assert is_supported_drive_file("Sheet", GOOGLE_MIME_SPREADSHEET) is True
    assert is_supported_drive_file("video.mp4", "video/mp4") is False


def test_is_google_native_mime():
    assert is_google_native_mime(GOOGLE_MIME_DOCUMENT) is True
    assert is_google_native_mime(GOOGLE_MIME_SPREADSHEET) is True
    assert is_google_native_mime("application/pdf") is False


def test_parse_drive_timestamp_iso8601():
    parsed = _parse_drive_timestamp("2026-09-01T04:46:44.213Z")
    assert parsed == datetime(2026, 9, 1, 4, 46, 44, 213000, tzinfo=UTC)


def test_parse_drive_timestamp_rfc2822():
    parsed = _parse_drive_timestamp("Mon, 01 Jan 2026 00:00:00 GMT")
    assert parsed == datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)


def test_parse_drive_timestamp_none_and_invalid():
    assert _parse_drive_timestamp(None) is None
    assert _parse_drive_timestamp("") is None
    assert _parse_drive_timestamp("not-a-date") is None
