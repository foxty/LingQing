"""Split user queries for hybrid FTS + vector retrieval."""

from __future__ import annotations

from apps.shared.search.publish.text import normalize_for_embedding


def prepare_search_queries(raw_query: str) -> tuple[str, str]:
    """Return (fts_query, vector_query) for hybrid search."""
    fts_query = (raw_query or "").strip()
    vector_query = normalize_for_embedding(raw_query)
    return fts_query, vector_query