#!/usr/bin/env python3
"""Migrate flat document originals into {doc_id}/original/{filename} layout.

Usage:
    uv run --env-file .env.local scripts/migrate_document_original_paths.py --dry-run
    uv run --env-file .env.local scripts/migrate_document_original_paths.py --tenant-id 1
    uv run --env-file .env.local scripts/migrate_document_original_paths.py
"""

# ruff: noqa: T201

from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from apps.config import get_tenant_documents_path
from apps.shared.db.session import app_db_session
from apps.shared.document.manifest import (
    document_original_relative_key,
    is_document_original_storage_key,
    normalize_document_filename,
)
from apps.shared.document.repository import DBDocumentRepository
from apps.shared.infra.storage.paths import is_cloud_storage_ref, resolve_storage_ref
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.tenant.repository import TenantRepository

logger = get_logger(__name__)

_IGNORED_ORPHAN_FILES = frozenset({".DS_Store"})


def _is_empty_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    for child in path.iterdir():
        if child.name in _IGNORED_ORPHAN_FILES:
            continue
        if child.is_dir():
            if not _is_empty_dir(child):
                return False
        else:
            return False
    return True


def _remove_empty_parents(path: Path, *, stop_at: Path, dry_run: bool) -> int:
    removed = 0
    current = path
    while current != stop_at and current.is_dir() and _is_empty_dir(current):
        if dry_run:
            print(f"[dry-run] remove empty dir: {current}")
        else:
            current.rmdir()
            logger.info("document_original_migration_removed_empty_dir path=%s", current)
        removed += 1
        current = current.parent
    return removed


def cleanup_orphan_document_dirs(tenant_id: int, *, dry_run: bool) -> int:
    """Remove leftover non-doc_id folders under documents/ (e.g. from slash filenames)."""
    docs_root = Path(get_tenant_documents_path(tenant_id))
    if not docs_root.exists():
        return 0

    removed = 0
    for entry in sorted(docs_root.iterdir(), key=lambda p: p.name):
        if not entry.is_dir() or entry.name.isdigit():
            continue
        if not _is_empty_dir(entry):
            logger.warning("document_orphan_cleanup_skipped_non_empty path=%s", entry)
            continue
        if dry_run:
            print(f"[dry-run] remove orphan dir tree: {entry}")
        else:
            shutil.rmtree(entry)
            logger.info("document_orphan_cleanup_removed path=%s", entry)
        removed += 1
    return removed


async def _resolve_tenant_ids(tenant_id: int | None) -> list[int]:
    if tenant_id is not None:
        return [tenant_id]
    async with app_db_session() as session:
        tenants = await TenantRepository(session).get_active_tenants()
        return [tenant.id for tenant in tenants]


async def migrate_tenant(
    tenant_id: int,
    *,
    dry_run: bool,
) -> tuple[int, int, int]:
    """Migrate one tenant. Returns (migrated, skipped, missing)."""
    migrated = 0
    skipped = 0
    missing = 0

    async with app_db_session() as session:
        repo = DBDocumentRepository(session)
        documents = await repo.list_by_tenant(tenant_id)

        for document in documents:
            if is_cloud_storage_ref(document.file_url):
                skipped += 1
                continue

            if is_document_original_storage_key(document.id, document.file_url):
                skipped += 1
                continue

            new_key = document_original_relative_key(document.id, document.filename)
            if document.file_url.replace("\\", "/") == new_key:
                skipped += 1
                continue

            old_resolved = resolve_storage_ref(tenant_id, document.file_url)
            new_resolved = resolve_storage_ref(tenant_id, new_key)
            old_path = Path(old_resolved)
            new_path = Path(new_resolved)

            if dry_run:
                if old_path.exists():
                    print(f"[dry-run] tenant={tenant_id} doc={document.id}: {old_path} -> {new_path}")
                    migrated += 1
                elif new_path.exists():
                    print(f"[dry-run] tenant={tenant_id} doc={document.id}: update file_url only -> {new_key}")
                    migrated += 1
                else:
                    print(f"[dry-run] tenant={tenant_id} doc={document.id}: source missing ({old_resolved})")
                    missing += 1
                continue

            if new_path.exists() and not old_path.exists():
                logger.info(
                    "document_original_migration_file_already_in_place tenant_id=%s document_id=%s path=%s",
                    tenant_id,
                    document.id,
                    new_path,
                )
            elif old_path.exists():
                new_path.parent.mkdir(parents=True, exist_ok=True)
                if new_path.exists():
                    backup = new_path.with_suffix(new_path.suffix + ".bak")
                    shutil.move(new_path, backup)
                shutil.move(old_path, new_path)
                docs_root = Path(get_tenant_documents_path(tenant_id))
                _remove_empty_parents(old_path.parent, stop_at=docs_root, dry_run=False)
                logger.info(
                    "document_original_migration_moved tenant_id=%s document_id=%s from=%s to=%s",
                    tenant_id,
                    document.id,
                    old_path,
                    new_path,
                )
            else:
                logger.warning(
                    "document_original_migration_source_missing tenant_id=%s document_id=%s path=%s",
                    tenant_id,
                    document.id,
                    old_path,
                )
                missing += 1
                continue

            stored_filename = normalize_document_filename(document.filename)
            await repo.update_document_file(
                document.id,
                tenant_id,
                filename=stored_filename,
                file_url=new_key,
                file_size=document.file_size,
                file_hash=document.file_hash,
            )
            migrated += 1

        if not dry_run and migrated:
            await session.commit()

    return migrated, skipped, missing


async def normalize_filenames(tenant_id: int, *, dry_run: bool) -> int:
    """Normalize DB filenames that still contain path separators."""
    updated = 0
    async with app_db_session() as session:
        repo = DBDocumentRepository(session)
        documents = await repo.list_by_tenant(tenant_id)
        for document in documents:
            stored_filename = normalize_document_filename(document.filename)
            if stored_filename == document.filename:
                continue
            if dry_run:
                print(
                    f"[dry-run] tenant={tenant_id} doc={document.id}: "
                    f"filename {document.filename!r} -> {stored_filename!r}"
                )
            else:
                await repo.update_document_file(
                    document.id,
                    tenant_id,
                    filename=stored_filename,
                    file_url=document.file_url,
                    file_size=document.file_size,
                    file_hash=document.file_hash,
                )
                logger.info(
                    "document_filename_normalized tenant_id=%s document_id=%s filename=%s",
                    tenant_id,
                    document.id,
                    stored_filename,
                )
            updated += 1
        if not dry_run and updated:
            await session.commit()
    return updated


async def handle_migrate(args: argparse.Namespace) -> int:
    tenant_ids = await _resolve_tenant_ids(args.tenant_id)
    if not tenant_ids:
        print("No tenants found")
        return 0

    total_migrated = 0
    total_skipped = 0
    total_missing = 0
    total_orphans = 0
    total_filenames = 0

    for tenant_id in tenant_ids:
        if not args.cleanup_orphans_only:
            migrated, skipped, missing = await migrate_tenant(tenant_id, dry_run=args.dry_run)
            total_migrated += migrated
            total_skipped += skipped
            total_missing += missing
            print(
                f"tenant={tenant_id}: migrated={migrated} skipped={skipped} missing={missing}"
                + (" (dry-run)" if args.dry_run else "")
            )

        if args.cleanup_orphans or args.cleanup_orphans_only:
            orphans = cleanup_orphan_document_dirs(tenant_id, dry_run=args.dry_run)
            total_orphans += orphans
            print(f"tenant={tenant_id}: orphan_dirs_removed={orphans}" + (" (dry-run)" if args.dry_run else ""))

        if args.normalize_filenames:
            filenames = await normalize_filenames(tenant_id, dry_run=args.dry_run)
            total_filenames += filenames
            print(f"tenant={tenant_id}: filenames_normalized={filenames}" + (" (dry-run)" if args.dry_run else ""))

    print(
        f"Done: migrated={total_migrated} skipped={total_skipped} missing={total_missing} "
        f"orphan_dirs_removed={total_orphans} filenames_normalized={total_filenames}"
        + (" (dry-run)" if args.dry_run else "")
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate document originals into per-document folders")
    parser.add_argument("--tenant-id", type=int, help="Migrate a single tenant (default: all active tenants)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned moves without changing files or database rows",
    )
    parser.add_argument(
        "--cleanup-orphans",
        action="store_true",
        help="Remove empty non-doc_id folder trees left after migration",
    )
    parser.add_argument(
        "--cleanup-orphans-only",
        action="store_true",
        help="Only remove orphan folder trees; skip file migration",
    )
    parser.add_argument(
        "--normalize-filenames",
        action="store_true",
        help="Flatten slash-containing filenames in the documents table",
    )
    args = parser.parse_args()
    return asyncio.run(handle_migrate(args))


if __name__ == "__main__":
    raise SystemExit(main())
