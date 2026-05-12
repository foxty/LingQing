from types import SimpleNamespace

from apps.shared.document.schemas import DocumentChunk, DocumentSearchResult
from apps.shared.search.schemas import ApiConnectorSearchResult, AssetSearchResult
from apps.shared.search.search_service import SearchService


def test_shared_rrf_helper_scores_and_sources():
    fts_items = [SimpleNamespace(uid="a"), SimpleNamespace(uid="b")]
    vector_items = [SimpleNamespace(uid="b"), SimpleNamespace(uid="c")]

    merged = SearchService._merge_ranked_results_rrf(
        fts_items=fts_items,
        vector_items=vector_items,
        key_fn=lambda item: item.uid,
        fts_weight=0.5,
        vector_weight=0.5,
        k=60,
    )

    assert [item["key"] for item in merged] == ["b", "a", "c"]
    assert merged[0]["source"] == "hybrid"
    assert merged[0]["score"] > merged[1]["score"]
    assert merged[1]["source"] == "fts"
    assert merged[2]["source"] == "vector"


def test_merge_document_results_rrf_merges_chunks_and_scores():
    service = SearchService.__new__(SearchService)

    fts = [
        DocumentSearchResult(
            doc_id=10,
            collection_id=1,
            filename="doc-a.pdf",
            source="fts",
            highlight="match",
            chunks=[DocumentChunk(chunk_index=0, content="chunk-0")],
        )
    ]
    vec = [
        DocumentSearchResult(
            doc_id=10,
            collection_id=1,
            filename="doc-a.pdf",
            source="vector",
            chunks=[
                DocumentChunk(chunk_index=0, content="chunk-0-dup"),
                DocumentChunk(chunk_index=1, content="chunk-1"),
            ],
        )
    ]

    merged = service._merge_document_results_rrf(fts, vec, 0.4, 0.6)

    assert len(merged) == 1
    result = merged[0]
    assert result.doc_id == 10
    assert result.source == "hybrid"
    assert result.rrf_score is not None
    assert result.rrf_score > 0
    assert [chunk.chunk_index for chunk in result.chunks] == [0, 1]


def test_merge_asset_results_rrf_sets_score_and_source():
    service = SearchService.__new__(SearchService)

    fts = [
        AssetSearchResult(
            asset_id=1,
            data_source_id=11,
            data_source_name="ds",
            data_source_type="postgres",
            asset_name="orders",
            asset_type="table",
            columns=[],
            row_count=100,
            source="fts",
        )
    ]
    vec = [
        AssetSearchResult(
            asset_id=1,
            data_source_id=11,
            data_source_name="ds",
            data_source_type="postgres",
            asset_name="orders",
            asset_type="table",
            columns=[],
            row_count=100,
            source="vector",
        )
    ]

    merged = service._merge_asset_results_rrf(fts, vec, 0.5, 0.5)

    assert len(merged) == 1
    assert merged[0].asset_id == 1
    assert merged[0].source == "hybrid"
    assert merged[0].rrf_score is not None
    assert merged[0].rrf_score > 0


def test_merge_api_connector_results_rrf_sets_score_and_source():
    service = SearchService.__new__(SearchService)

    fts = [
        ApiConnectorSearchResult(
            operation_uid="a",
            connector_id=1,
            connector_name="API",
            method="GET",
            path_template="/a",
            operation_id=10,
            source="fts",
        ),
        ApiConnectorSearchResult(
            operation_uid="b",
            connector_id=1,
            connector_name="API",
            method="POST",
            path_template="/b",
            operation_id=11,
            source="fts",
        ),
    ]
    vec = [
        ApiConnectorSearchResult(
            operation_uid="b",
            connector_id=1,
            connector_name="API",
            method="POST",
            path_template="/b",
            operation_id=11,
            source="vector",
        ),
    ]

    merged = service._merge_api_connector_results_rrf(fts, vec, 0.5, 0.5)

    assert len(merged) == 2
    assert merged[0].operation_uid == "b"
    assert merged[0].source == "hybrid"
    assert merged[0].rrf_score is not None
    assert merged[0].rrf_score > merged[1].rrf_score
    assert merged[1].source == "fts"
    assert all(r.rrf_score is not None and r.rrf_score > 0 for r in merged)
