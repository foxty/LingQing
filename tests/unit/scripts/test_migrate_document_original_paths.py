"""Unit tests for migrate_document_original_paths script helpers."""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.migrate_document_original_paths import (  # noqa: E402
    _remove_empty_parents,
    cleanup_orphan_document_dirs,
    migrate_tenant,
    normalize_filenames,
)


@pytest.fixture
def tenant_docs_root(tmp_path, monkeypatch):
    docs_root = tmp_path / "tenants" / "tenant_1" / "documents"
    docs_root.mkdir(parents=True)

    def _get_tenant_documents_path(tenant_id: int | str) -> str:
        root = tmp_path / "tenants" / f"tenant_{tenant_id}" / "documents"
        root.mkdir(parents=True, exist_ok=True)
        return str(root)

    monkeypatch.setattr("scripts.migrate_document_original_paths.get_tenant_documents_path", _get_tenant_documents_path)
    monkeypatch.setattr("apps.shared.infra.storage.paths.get_tenant_documents_path", _get_tenant_documents_path)
    monkeypatch.setattr("apps.config.get_tenant_documents_path", _get_tenant_documents_path)
    return docs_root


def test_remove_empty_parents_removes_nested_orphan_tree(tenant_docs_root):
    nested = tenant_docs_root / "CMS Search - 2026" / "09"
    nested.mkdir(parents=True)

    removed = _remove_empty_parents(nested, stop_at=tenant_docs_root, dry_run=False)

    assert removed == 2
    assert not (tenant_docs_root / "CMS Search - 2026").exists()


def test_cleanup_orphan_document_dirs_removes_empty_title_folders(tenant_docs_root):
    orphan = tenant_docs_root / "CMS Search - 2026"
    (orphan / "09").mkdir(parents=True)
    (tenant_docs_root / "7").mkdir()
    (tenant_docs_root / "7" / "original").mkdir(parents=True)

    removed = cleanup_orphan_document_dirs(1, dry_run=False)

    assert removed == 1
    assert not orphan.exists()
    assert (tenant_docs_root / "7").exists()


def test_cleanup_orphan_document_dirs_skips_non_empty_title_folder(tenant_docs_root):
    orphan = tenant_docs_root / "CMS Search - 2026"
    orphan.mkdir()
    (orphan / "notes.docx").write_bytes(b"still here")

    removed = cleanup_orphan_document_dirs(1, dry_run=False)

    assert removed == 0
    assert orphan.exists()


@pytest.mark.asyncio
async def test_migrate_tenant_moves_nested_flat_file_and_cleans_parents(tenant_docs_root, monkeypatch):
    raw_filename = "CMS Search - 2026/09/01 notes.docx"
    old_relative = "CMS Search - 2026/09/01 notes.docx"
    old_path = tenant_docs_root / old_relative
    old_path.parent.mkdir(parents=True, exist_ok=True)
    old_path.write_bytes(b"migrated-content")

    document = MagicMock()
    document.id = 7
    document.filename = raw_filename
    document.file_url = old_relative
    document.file_size = len(b"migrated-content")
    document.file_hash = "abc123"

    mock_repo = AsyncMock()
    mock_repo.list_by_tenant = AsyncMock(return_value=[document])
    mock_repo.update_document_file = AsyncMock()

    @asynccontextmanager
    async def mock_app_db_session():
        session = MagicMock()
        session.commit = AsyncMock()
        yield session

    monkeypatch.setattr("scripts.migrate_document_original_paths.app_db_session", mock_app_db_session)
    monkeypatch.setattr("scripts.migrate_document_original_paths.DBDocumentRepository", lambda _session: mock_repo)

    migrated, skipped, missing = await migrate_tenant(1, dry_run=False)

    new_path = tenant_docs_root / "7" / "original" / "CMS Search - 2026 - 09 - 01 notes.docx"
    assert migrated == 1
    assert skipped == 0
    assert missing == 0
    assert new_path.exists()
    assert new_path.read_bytes() == b"migrated-content"
    assert not old_path.exists()
    assert not (tenant_docs_root / "CMS Search - 2026").exists()

    update_kwargs = mock_repo.update_document_file.await_args.kwargs
    assert update_kwargs["filename"] == "CMS Search - 2026 - 09 - 01 notes.docx"
    assert update_kwargs["file_url"] == "7/original/CMS Search - 2026 - 09 - 01 notes.docx"


@pytest.mark.asyncio
async def test_normalize_filenames_updates_slash_containing_rows(tenant_docs_root, monkeypatch):
    document = MagicMock()
    document.id = 8
    document.filename = "Title - 2026/08/06 notes.docx"
    document.file_url = "8/original/06 notes.docx"
    document.file_size = 10
    document.file_hash = "hash"

    mock_repo = AsyncMock()
    mock_repo.list_by_tenant = AsyncMock(return_value=[document])
    mock_repo.update_document_file = AsyncMock()

    @asynccontextmanager
    async def mock_app_db_session():
        session = MagicMock()
        session.commit = AsyncMock()
        yield session

    monkeypatch.setattr("scripts.migrate_document_original_paths.app_db_session", mock_app_db_session)
    monkeypatch.setattr("scripts.migrate_document_original_paths.DBDocumentRepository", lambda _session: mock_repo)

    updated = await normalize_filenames(1, dry_run=False)

    assert updated == 1
    update_kwargs = mock_repo.update_document_file.await_args.kwargs
    assert update_kwargs["filename"] == "Title - 2026 - 08 - 06 notes.docx"
