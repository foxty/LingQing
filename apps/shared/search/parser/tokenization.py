"""Tokenization helpers for PostgreSQL FTS."""

from __future__ import annotations

import jieba

from apps.shared.search.parser.normalization import preprocess_for_fts


def unified_tokenize(text: str) -> str:
    """Tokenize text using jieba for Chinese/English FTS."""
    if not text or not text.strip():
        return ""

    normalized = preprocess_for_fts(text)
    words = jieba.lcut(normalized)
    valid_words = [word for word in words if word.strip()]
    return " ".join(valid_words)
