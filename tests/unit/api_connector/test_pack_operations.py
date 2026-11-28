"""Unit tests for pack upsert/stale helpers (Protocol port, no database)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
import pytest

from apps.shared.external_systems.api_connector import pack_operations as pack_ops
from apps.shared.external_systems.api_connector.constants import (
    AUTH_REQUIREMENT_REQUIRED,
    OPERATION_SOURCE_MANUAL,
    OPERATION_STATUS_ACTIVE,
    OPERATION_STATUS_DISABLED,
    OPERATION_STATUS_STALE,
)
from apps.shared.external_systems.api_connector.domain import ApiOperationDomain


def _connector_stub(*, connector_id: int = 5, owner_id: int = 2) -> SimpleNamespace:
    return SimpleNamespace(id=connector_id, owner_id=owner_id)


def _pack_spec(**overrides) -> pack_ops.PackOperationSyncSpec:
    base = dict(
        method="POST",
        path_template="/items.search",
        operation_id="search_items",
        summary="Search",
        description=None,
        request_schema={"type": "object"},
        response_schema={"type": "object"},
        enabled=True,
        pack_id="test-pack",
    )
    base.update(overrides)
    return pack_ops.PackOperationSyncSpec(**base)


class _FakePackSession:
    def __init__(self) -> None:
        self.created: list[ApiOperationDomain] = []
        self.updated: list[ApiOperationDomain] = []
        self.refreshed: list[ApiOperationDomain] = []
        self.stale_removed: list[ApiOperationDomain] = []
        self.list_operations: list[ApiOperationDomain] = []

    async def create_operation_domain(self, operation: ApiOperationDomain) -> ApiOperationDomain:
        saved = replace(operation, id=101)
        self.created.append(saved)
        return saved

    async def update_operation_domain(self, operation: ApiOperationDomain) -> None:
        self.updated.append(operation)

    async def refresh_operation_resource_index(self, operation: ApiOperationDomain) -> None:
        self.refreshed.append(operation)

    async def remove_operation_resource_index(self, operation: ApiOperationDomain) -> None:
        self.stale_removed.append(operation)

    async def list_operation_domains_for_connector(self, connector_id: int) -> list[ApiOperationDomain]:
        del connector_id
        return list(self.list_operations)


@pytest.mark.asyncio
async def test_upsert_pack_operation_creates_when_missing():
    session = _FakePackSession()
    connector = _connector_stub()
    result = await pack_ops._upsert_pack_operation(session, connector, _pack_spec(), None)
    assert result == "added"
    assert len(session.created) == 1
    assert session.created[0].operation_id == "search_items"
    assert len(session.refreshed) == 1


@pytest.mark.asyncio
async def test_upsert_pack_operation_unchanged_when_hash_and_status_match():
    session = _FakePackSession()
    connector = _connector_stub()
    spec = _pack_spec()
    now = datetime.now(UTC)
    current = ApiOperationDomain.draft_pack_managed(
        connector_id=connector.id,
        owner_id=connector.owner_id,
        pack_id=spec.pack_id,
        method=spec.method,
        path_template=spec.path_template,
        operation_id=spec.operation_id,
        summary=spec.summary,
        description=spec.description,
        request_schema=spec.request_schema,
        response_schema=spec.response_schema,
        target_status=spec.target_status,
        operation_uid_seed=spec.operation_uid_seed,
        now=now,
    )
    current = replace(current, id=9, content_hash=spec.content_hash())
    result = await pack_ops._upsert_pack_operation(session, connector, spec, current)
    assert result == "unchanged"
    assert not session.updated


@pytest.mark.asyncio
async def test_upsert_pack_operation_updates_on_hash_change():
    session = _FakePackSession()
    connector = _connector_stub()
    spec = _pack_spec(summary="Search v2")
    now = datetime.now(UTC)
    current = ApiOperationDomain.draft_pack_managed(
        connector_id=connector.id,
        owner_id=connector.owner_id,
        pack_id=spec.pack_id,
        method=spec.method,
        path_template=spec.path_template,
        operation_id=spec.operation_id,
        summary="Search v1",
        description=spec.description,
        request_schema=spec.request_schema,
        response_schema=spec.response_schema,
        target_status=spec.target_status,
        operation_uid_seed=spec.operation_uid_seed,
        now=now,
    )
    current = replace(current, id=9, content_hash="stale-hash")
    result = await pack_ops._upsert_pack_operation(session, connector, spec, current)
    assert result == "updated"
    assert session.updated[0].summary == "Search v2"


@pytest.mark.asyncio
async def test_upsert_pack_operation_preserves_disabled_status_on_update():
    session = _FakePackSession()
    connector = _connector_stub()
    spec = _pack_spec(enabled=True)
    now = datetime.now(UTC)
    current = ApiOperationDomain.draft_pack_managed(
        connector_id=connector.id,
        owner_id=connector.owner_id,
        pack_id=spec.pack_id,
        method=spec.method,
        path_template=spec.path_template,
        operation_id=spec.operation_id,
        summary=spec.summary,
        description=spec.description,
        request_schema=spec.request_schema,
        response_schema=spec.response_schema,
        target_status=OPERATION_STATUS_DISABLED,
        operation_uid_seed=spec.operation_uid_seed,
        now=now,
    )
    current = replace(current, id=9, status=OPERATION_STATUS_DISABLED, content_hash="old")
    result = await pack_ops._upsert_pack_operation(session, connector, spec, current)
    assert result == "updated"
    assert session.updated[0].status == OPERATION_STATUS_DISABLED


@pytest.mark.asyncio
async def test_stale_removed_pack_operations_marks_removed_ops():
    session = _FakePackSession()
    now = datetime.now(UTC)
    kept = ApiOperationDomain(
        id=1,
        connector_id=5,
        operation_uid="uid-a",
        method="POST",
        path_template="/a",
        operation_id="op_a",
        summary="A",
        description=None,
        tags=["test-pack"],
        request_schema={},
        response_schema={},
        auth_requirement=AUTH_REQUIREMENT_REQUIRED,
        risk_level="medium",
        source=OPERATION_SOURCE_MANUAL,
        upstream_key="pack:op_a",
        content_hash="h",
        status=OPERATION_STATUS_ACTIVE,
        owner_id=2,
        created_at=now,
        updated_at=now,
    )
    removed = replace(kept, id=2, operation_uid="uid-b", operation_id="op_b", upstream_key="pack:op_b")
    session.list_operations = [kept, removed]
    staled = await pack_ops._stale_removed_pack_operations(
        session,
        connector_id=5,
        pack_id="test-pack",
        manifest_operation_ids={"op_a"},
    )
    assert staled == 1
    assert session.updated[0].status == OPERATION_STATUS_STALE
    assert session.stale_removed[0].operation_id == "op_b"