"""Unit tests for document duplicate upload error messages."""

from datetime import UTC, datetime

from apps.shared.document.service import DocumentService


def test_duplicate_content_message_different_filenames():
    message = DocumentService._duplicate_content_message(
        "2026-Peak-Season-Readiness.pptx",
        "2026 Website Performance Test Report.pptx",
        upload_date=datetime(2026, 9, 26, 11, 52, 52, tzinfo=UTC),
    )
    assert "2026-Peak-Season-Readiness.pptx" in message
    assert "2026 Website Performance Test Report.pptx" in message
    assert "内容相同" in message


def test_duplicate_content_message_same_filename():
    message = DocumentService._duplicate_content_message(
        "report.pdf",
        "report.pdf",
    )
    assert message == "该集合中已存在相同内容的文件 'report.pdf'。"
