#!/usr/bin/env python3
"""Regenerate Docling golden block files after a parser/image bump.

Run when you change deploy/env/docling.version or add integration fixtures.
Requires a running Docling service (local stack or testcontainer):

    DOCLING_SERVICE_URL=http://127.0.0.1:5001 uv run python scripts/update_docling_golden_blocks.py
    DOCLING_SERVICE_URL=http://127.0.0.1:5001 uv run python scripts/update_docling_golden_blocks.py --fixture mortgage_pdf
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("DATA_ROOT_PATH", tempfile.mkdtemp())
os.environ.setdefault("TENANT_APP_DB_USER", "test_user")
os.environ.setdefault("TENANT_APP_DB_PASSWORD", "test_password")
os.environ.setdefault("TENANT_APP_DB_NAME", "test_db")
os.environ.setdefault("TENANT_APP_DB_HOST", "localhost")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from apps.shared.document.domain import DocumentDomain  # noqa: E402
from apps.shared.document.parsers.docling import DoclingDocumentParser  # noqa: E402
from tests.helpers.parsing_quality import (  # noqa: E402
    integration_source_path,
    list_integration_fixtures,
    persist_integration_blocks,
    pinned_docling_image,
    write_blocks_golden,
)


class _LocalStorage:
    def __init__(self, content: bytes):
        self._content = content

    async def read(self, file_url: str) -> bytes:
        return self._content


def _build_document(source_path: Path) -> DocumentDomain:
    return DocumentDomain(
        id=1,
        tenant_id=1,
        collection_id=1,
        filename=source_path.name,
        file_url=source_path.name,
        file_size=source_path.stat().st_size,
        file_hash="fixture-hash",
        status="processing",
        owner_id=1,
        upload_date=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


async def _record(fixture_id: str | None) -> int:
    service_url = (os.environ.get("DOCLING_SERVICE_URL") or "").strip().rstrip("/")
    if not service_url:
        print("DOCLING_SERVICE_URL is required", file=sys.stderr)
        return 1

    print(f"Using Docling image pin: {pinned_docling_image()}")
    selected = {fixture_id} if fixture_id else set()
    recorded = 0
    for fixture in list_integration_fixtures():
        if selected and fixture["id"] not in selected:
            continue
        source_path = integration_source_path(fixture)
        if not source_path.exists():
            print(f"skip {fixture['id']}: missing {source_path.name}")
            continue

        parser = DoclingDocumentParser(_LocalStorage(source_path.read_bytes()))
        parser._base_url = service_url
        blocks_doc = await parser.parse(_build_document(source_path))
        blocks_doc = await persist_integration_blocks(blocks_doc)
        path = write_blocks_golden(blocks_doc, fixture)
        image_count = sum(
            1 for block in blocks_doc.get("blocks", []) if isinstance(block, dict) and block.get("type") == "image"
        )
        print(f"recorded {path.relative_to(PROJECT_ROOT)} ({image_count} image blocks)")
        recorded += 1

    return 0 if recorded else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", help="Only record the given fixture id")
    args = parser.parse_args()
    return asyncio.run(_record(args.fixture))


if __name__ == "__main__":
    raise SystemExit(main())
