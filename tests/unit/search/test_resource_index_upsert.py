"""Tests for ResourceIndexRepository parse-pointer upsert behavior."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from apps.shared.search.repository import ResourceIndexRepository


@pytest.mark.asyncio
async def test_upsert_does_not_clear_existing_raw_content_when_none():
    db = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    repo = ResourceIndexRepository(db)
    existing = SimpleNamespace(
        id=9,
        vector_status="pending",
        raw_content={"storage_uri": "15/parsed/latest/blocks.json", "schema_version": 1},
    )
    repo.get_by_resource = AsyncMock(return_value=existing)

    await repo.upsert(
        tenant_id=2,
        resource_type="document",
        resource_id=15,
        owner_id=1,
        raw_content=None,
        content_updated_at=datetime.now(UTC),
        parent_id=1,
        source_parser="docling",
    )

    stmt = db.execute.await_args.args[0]
    compiled = stmt.compile()
    assert "raw_content" not in compiled.params


@pytest.mark.asyncio
async def test_upsert_writes_raw_content_when_provided():
    db = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    repo = ResourceIndexRepository(db)
    existing = SimpleNamespace(id=9, vector_status="pending", raw_content=None)
    repo.get_by_resource = AsyncMock(return_value=existing)
    pointer = {"storage_uri": "15/parsed/latest/blocks.json", "schema_version": 1}

    await repo.upsert(
        tenant_id=2,
        resource_type="document",
        resource_id=15,
        owner_id=1,
        raw_content=pointer,
        content_updated_at=datetime.now(UTC),
        parent_id=1,
        source_parser="docling",
    )

    stmt = db.execute.await_args.args[0]
    compiled = stmt.compile()
    assert compiled.params.get("raw_content") == pointer
