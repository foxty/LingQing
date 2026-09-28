"""Live Docling parsing integration tests against binary fixtures.

Uses the image pin in ``deploy/env/docling.version`` (via testcontainers).
Compares parser output to committed goldens under ``tests/fixtures/parsing/baselines/``.
Regenerate goldens after a Docling bump: ``scripts/update_docling_golden_blocks.py``.
Goldens must be produced on ``linux/amd64`` (same as CI testcontainers).

    uv run pytest tests/docling_integration/ -m docling -s
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime

import pytest

from apps.shared.document.domain import DocumentDomain
from apps.shared.document.parsers.docling import DoclingDocumentParser
from tests.helpers.parsing_quality import (
    assert_integration_golden,
    integration_baseline_path,
    integration_source_path,
    list_integration_fixtures,
    persist_integration_blocks,
)

pytestmark = [pytest.mark.docling, pytest.mark.integration, pytest.mark.slow]


class _LocalStorage:
    def __init__(self, content: bytes):
        self._content = content

    async def read(self, file_url: str) -> bytes:
        return self._content


def _build_document(source_path) -> DocumentDomain:
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


@pytest.mark.parametrize("fixture", list_integration_fixtures(), ids=lambda item: item["id"])
@pytest.mark.asyncio
async def test_docling_parse_matches_golden_blocks(fixture, docling_service_url):
    source_path = integration_source_path(fixture)
    if not source_path.exists():
        pytest.skip(f"missing source file: {source_path.name}")

    print(
        f"[docling-integration] Parsing {fixture['id']} ({source_path.name})...",
        file=sys.stderr,
        flush=True,
    )
    parser = DoclingDocumentParser(_LocalStorage(source_path.read_bytes()))
    parser._base_url = docling_service_url.rstrip("/")
    blocks_doc = await parser.parse(_build_document(source_path))
    blocks_doc = await persist_integration_blocks(blocks_doc)

    assert blocks_doc["parser"] == "docling"
    assert blocks_doc.get("blocks")

    baseline_path = integration_baseline_path(fixture)
    if not baseline_path.exists():
        pytest.fail(
            f"Missing baseline {baseline_path.name}. "
            f"Regenerate with: DOCLING_SERVICE_URL=<url> uv run python scripts/update_docling_golden_blocks.py "
            f"--fixture {fixture['id']}"
        )
    assert_integration_golden(blocks_doc, fixture)
    print(f"[docling-integration] OK {fixture['id']}", file=sys.stderr, flush=True)
