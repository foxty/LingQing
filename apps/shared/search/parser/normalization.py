"""Text normalization helpers for vector and FTS indexing."""

from __future__ import annotations

import re

from nltk.stem import SnowballStemmer

_SEPARATOR_RE = re.compile(r"[_-]+")
_WHITESPACE_RE = re.compile(r"\s+")
_ENGLISH_WORD_RE = re.compile(r"[a-zA-Z]+")

_stemmer: SnowballStemmer | None = None


def _get_stemmer() -> SnowballStemmer:
    global _stemmer
    if _stemmer is None:
        _stemmer = SnowballStemmer("english")
    return _stemmer


def _split_separators_and_lowercase(text: str) -> str:
    text = text.lower()
    text = _SEPARATOR_RE.sub(" ", text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def normalize_for_embedding(text: str) -> str:
    """Light normalization for vector embedding index and queries."""
    if not text:
        return ""
    return _split_separators_and_lowercase(text)


def preprocess_for_fts(text: str) -> str:
    """FTS text preprocessing: separator split plus English Snowball stemming."""
    if not text:
        return ""

    text = _split_separators_and_lowercase(text)
    stemmer = _get_stemmer()

    def _stem_match(match: re.Match) -> str:
        return stemmer.stem(match.group(0))

    text = _ENGLISH_WORD_RE.sub(_stem_match, text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def preprocess_text(text: str) -> str:
    """Backward-compatible alias for :func:`preprocess_for_fts`."""
    return preprocess_for_fts(text)


def prepare_search_queries(raw_query: str) -> tuple[str, str]:
    """Split a user query for hybrid search."""
    fts_query = (raw_query or "").strip()
    vector_query = normalize_for_embedding(raw_query)
    return fts_query, vector_query
