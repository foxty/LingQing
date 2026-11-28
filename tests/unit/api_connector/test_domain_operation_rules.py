"""Domain rules for API operation catalog identity and pack ownership."""

from apps.shared.external_systems.api_connector.constants import (
    AUTH_REQUIREMENT_REQUIRED,
    OPERATION_SOURCE_IMPORTED,
    OPERATION_SOURCE_MANUAL,
    OPERATION_STATUS_ACTIVE,
    OPERATION_STATUS_DISABLED,
    OPERATION_STATUS_STALE,
)
from apps.shared.external_systems.api_connector.domain import ApiOperationDomain
from apps.shared.core.exceptions import ValidationError
from datetime import UTC, datetime
import pytest


def _sample_operation(**overrides) -> ApiOperationDomain:
    now = datetime.now(UTC)
    base = dict(
        id=1,
        connector_id=9,
        operation_uid="uid",
        method="GET",
        path_template="/items",
        operation_id="list_items",
        summary="List",
        description=None,
        tags=["slack-user"],
        request_schema={},
        response_schema={},
        auth_requirement=AUTH_REQUIREMENT_REQUIRED,
        risk_level="medium",
        source=OPERATION_SOURCE_MANUAL,
        upstream_key="pack:list_items",
        content_hash="abc",
        status=OPERATION_STATUS_ACTIVE,
        owner_id=3,
        created_at=now,
        updated_at=now,
    )
    base.update(overrides)
    return ApiOperationDomain(**base)


def test_compute_content_hash_is_stable():
    a = ApiOperationDomain.compute_content_hash(
        method="GET",
        path_template="/x",
        operation_id="x",
        summary="s",
        description=None,
        tags=["t"],
        request_schema={},
        response_schema={},
        auth_requirement=AUTH_REQUIREMENT_REQUIRED,
    )
    b = ApiOperationDomain.compute_content_hash(
        method="GET",
        path_template="/x",
        operation_id="x",
        summary="s",
        description=None,
        tags=["t"],
        request_schema={},
        response_schema={},
        auth_requirement=AUTH_REQUIREMENT_REQUIRED,
    )
    assert a == b


def test_draft_pack_managed_sets_pack_upstream_and_tag():
    draft = ApiOperationDomain.draft_pack_managed(
        connector_id=2,
        owner_id=1,
        pack_id="slack-user",
        method="POST",
        path_template="/search",
        operation_id="slack_search",
        summary="Search",
        description=None,
        request_schema={"type": "object"},
        response_schema={"type": "object"},
        target_status=OPERATION_STATUS_ACTIVE,
        operation_uid_seed="POST:/search:slack_search",
    )
    assert draft.upstream_key == "pack:slack_search"
    assert draft.tags == ["slack-user"]
    assert draft.source == OPERATION_SOURCE_MANUAL
    assert draft.content_hash == draft.spec_content_hash()


def test_draft_imported_from_fields_sets_upstream_and_hash():
    draft = ApiOperationDomain.draft_imported_from_fields(
        connector_id=2,
        owner_id=1,
        method="GET",
        path_template="/items",
        operation_id="list",
        summary="List",
        description=None,
        tags=["a"],
        request_schema={},
        response_schema={},
        auth_requirement=AUTH_REQUIREMENT_REQUIRED,
    )
    assert draft.upstream_key == ApiOperationDomain.build_upstream_key("GET", "/items")
    assert draft.content_hash == draft.spec_content_hash()
    assert draft.source == OPERATION_SOURCE_IMPORTED


def test_build_pack_upstream_key_matches_pack_prefix():
    assert ApiOperationDomain.build_pack_upstream_key("list_items") == "pack:list_items"


def test_is_pack_managed_by_tag_or_upstream():
    op = _sample_operation(tags=["slack-user"], upstream_key=None)
    assert op.is_pack_managed("slack-user")
    op2 = _sample_operation(tags=[], upstream_key="pack:list_items")
    assert op2.is_pack_managed("other-pack")


def test_assert_runnable_for_execution_rejects_disabled():
    op = _sample_operation(status=OPERATION_STATUS_DISABLED)
    with pytest.raises(ValidationError):
        op.assert_runnable_for_execution()


def test_needs_openapi_resync_stale_or_hash_change():
    current = _sample_operation(content_hash="old", status=OPERATION_STATUS_ACTIVE)
    incoming = _sample_operation(content_hash="new")
    assert current.needs_openapi_resync(incoming)
    stale = _sample_operation(content_hash="old", status=OPERATION_STATUS_STALE)
    same_hash = _sample_operation(content_hash="old")
    assert stale.needs_openapi_resync(same_hash)
    assert not current.needs_openapi_resync(_sample_operation(content_hash="old"))


def test_apply_openapi_import_preserves_disabled():
    now = datetime.now(UTC)
    current = _sample_operation(status=OPERATION_STATUS_DISABLED, content_hash="old")
    incoming = _sample_operation(content_hash="new", summary="Updated")
    updated = current.apply_openapi_import(incoming, at=now)
    assert updated.status == OPERATION_STATUS_DISABLED
    assert updated.summary == "Updated"
    assert updated.content_hash == "new"


def test_marked_stale():
    now = datetime.now(UTC)
    op = _sample_operation()
    stale = op.marked_stale(at=now)
    assert stale.status == OPERATION_STATUS_STALE
    assert stale.updated_at == now