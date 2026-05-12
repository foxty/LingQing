from apps.shared.domain.types import (
    SEARCH_TARGET_API_CONNECTOR,
    SEARCH_TARGET_ASSET,
    SEARCH_TARGET_BOTH,
    SEARCH_TARGET_DOCUMENT,
)
from apps.shared.search.schemas import ApiConnectorSearchResult, SearchResultItem, SearchTarget


def test_search_target_constants_are_strict_canonical_values():
    assert SearchTarget.DOCUMENT == SEARCH_TARGET_DOCUMENT
    assert SearchTarget.ASSET == SEARCH_TARGET_ASSET
    assert SearchTarget.API_CONNECTOR == SEARCH_TARGET_API_CONNECTOR
    assert SearchTarget.BOTH == SEARCH_TARGET_BOTH


def test_api_connector_result_to_unified_item():
    op = ApiConnectorSearchResult(
        operation_uid="uid-1",
        connector_id=7,
        connector_name="CRM",
        method="GET",
        path_template="/customers/{id}",
        operation_id=42,
        summary="Get customer by id",
        description="Returns customer profile",
        tags=["customers"],
        source="fts",
    )

    item = SearchResultItem(
        resource_type="api_connector",
        resource_id=op.operation_id,
        title=f"{op.method} {op.path_template}",
        score=op.rrf_score,
        source=op.source,
        snippet=op.summary,
        contents=[
            {
                "operation_uid": op.operation_uid,
                "connector_id": op.connector_id,
                "method": op.method,
                "path_template": op.path_template,
                "summary": op.summary,
                "description": op.description,
                "tags": op.tags,
                "connector_name": op.connector_name,
            }
        ],
    )

    assert item.resource_type == "api_connector"
    assert item.resource_id == 42
    assert item.title == "GET /customers/{id}"
    assert item.contents[0]["connector_name"] == "CRM"
    assert item.contents[0]["connector_id"] == 7
