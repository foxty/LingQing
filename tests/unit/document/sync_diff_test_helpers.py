"""Shared stubs for document sync diff unit tests."""

from __future__ import annotations

from unittest.mock import AsyncMock

from apps.shared.document.sync_service import DocumentSyncService


def stub_healthy_listable_mapping(sync_service: DocumentSyncService) -> None:
    """Map is unchanged-only when the linked document still exists in the collection list."""
    sync_service._mapping_document_listable = AsyncMock(return_value=True)
    sync_service._document_is_deleted = AsyncMock(return_value=False)