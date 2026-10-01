"""Unit tests for context resource search service and repository behavior."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import sqlite

from apps.shared.context_resource.domain import ContextResourceItem, ContextResourceKey
from apps.shared.context_resource.repository import ContextResourceRepository
from apps.shared.context_resource.service import ContextResourceSearchService


@pytest.mark.asyncio
async def test_service_delegates_search_to_repository():
    repo = MagicMock()
    repo.search = AsyncMock(
        return_value=[
            MagicMock(
                resource_type="document",
                resource_id=1,
                title="doc-a",
                subtitle=None,
            )
        ]
    )
    service = ContextResourceSearchService(tenant_id=99, db_session=MagicMock())
    service._repo = repo

    results = await service.search(query="doc", limit=5)

    repo.search.assert_awaited_once_with(tenant_id=99, query="doc", limit_per_type=5)
    assert len(results) == 1


@pytest.mark.asyncio
async def test_repository_empty_query_uses_wildcard_pattern():
    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            _rows_result([]),
            _rows_result([]),
            _rows_result([]),
            _rows_result([]),
            _rows_result([]),
            _rows_result([]),
        ]
    )
    repo = ContextResourceRepository(db)

    results = await repo.search(tenant_id=1, query="", limit_per_type=3)

    assert results == []
    assert db.execute.await_count == 6
    asset_call = db.execute.await_args_list[5]
    asset_sql = asset_call.args[0].text
    assert "ds.tenant_id" in asset_sql
    assert "am.tenant_id" not in asset_sql
    assert asset_call.args[1]["pattern"] == "%%"


@pytest.mark.asyncio
async def test_service_delegates_resolve_to_repository():
    repo = MagicMock()
    repo.resolve_by_refs = AsyncMock(
        return_value=[
            ContextResourceItem(
                resource_type="document",
                resource_id=2,
                title="doc-a",
            )
        ]
    )
    service = ContextResourceSearchService(tenant_id=99, db_session=MagicMock())
    service._repo = repo

    refs = [ContextResourceKey(resource_type="document", resource_id=2)]
    results = await service.resolve_by_refs(refs)

    repo.resolve_by_refs.assert_awaited_once_with(99, refs)
    assert len(results) == 1
    assert results[0].title == "doc-a"


@pytest.mark.asyncio
async def test_resolve_by_refs_document_found():
    mock_document = MagicMock()
    mock_document.title = None
    mock_document.name = None
    mock_document.filename = "sample-report-acme.pdf"

    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = mock_document
    db = MagicMock()
    db.execute = AsyncMock(return_value=execute_result)
    repo = ContextResourceRepository(db)

    refs = [ContextResourceKey(resource_type="document", resource_id=2)]
    items = await repo.resolve_by_refs(tenant_id=2, refs=refs)

    assert len(items) == 1
    assert items[0].title == "sample-report-acme.pdf"
    assert items[0].subtitle is None


@pytest.mark.asyncio
async def test_resolve_by_refs_asset_scopes_by_data_source_tenant():
    mock_asset = MagicMock()
    mock_asset.asset_name = "sales_orders"

    execute_result = MagicMock()
    execute_result.one_or_none.return_value = (mock_asset, "Databricks")
    db = MagicMock()
    db.execute = AsyncMock(return_value=execute_result)
    repo = ContextResourceRepository(db)

    refs = [ContextResourceKey(resource_type="asset", resource_id=9)]
    items = await repo.resolve_by_refs(tenant_id=2, refs=refs)

    assert len(items) == 1
    assert items[0].title == "sales_orders"
    assert items[0].subtitle == "Databricks"


@pytest.mark.asyncio
async def test_resolve_by_refs_marks_missing_resource():
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    db = MagicMock()
    db.execute = AsyncMock(return_value=execute_result)
    repo = ContextResourceRepository(db)

    refs = [ContextResourceKey(resource_type="dashboard", resource_id=404)]
    items = await repo.resolve_by_refs(tenant_id=2, refs=refs)

    assert len(items) == 1
    assert items[0].title == "dashboard #404"
    assert items[0].subtitle == "not found"


@pytest.mark.asyncio
async def test_resolve_by_refs_unknown_type():
    db = MagicMock()
    db.execute = AsyncMock()
    repo = ContextResourceRepository(db)

    refs = [ContextResourceKey(resource_type="widget", resource_id=1)]
    items = await repo.resolve_by_refs(tenant_id=2, refs=refs)

    assert len(items) == 1
    assert items[0].title == "Unknown widget"
    db.execute.assert_not_awaited()


def _rows_result(rows: list[tuple]):
    result = MagicMock()
    result.all.return_value = rows
    return result


@pytest.mark.asyncio
async def test_search_scheduled_tasks_excludes_system_tasks():
    db = MagicMock()
    db.execute = AsyncMock(return_value=_rows_result([(7, "User nightly job")]))
    repo = ContextResourceRepository(db)

    items = await repo._search_scheduled_tasks(tenant_id=1, query="job", limit=5)

    assert len(items) == 1
    assert items[0].resource_type == "scheduled_task"
    assert items[0].resource_id == 7
    assert items[0].title == "User nightly job"
    stmt = db.execute.await_args.args[0]
    sql = str(stmt.compile(dialect=sqlite.dialect())).lower()
    assert "stable_key" in sql
    assert "is null" in sql
