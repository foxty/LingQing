"""Extract and normalize text for publish (FTS + vector chunk bodies)."""

from __future__ import annotations

import re

import jieba
from nltk.stem import SnowballStemmer

from apps.shared.document.manifest import is_manifest_pointer

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


def extract_text_from_raw(raw_content: dict) -> str:
    """Extract plain text from raw_content for tokenization."""
    if not raw_content:
        return ""

    if is_manifest_pointer(raw_content):
        return ""

    text = raw_content.get("text")
    if text and isinstance(text, str):
        return text

    content = raw_content.get("content")
    if not content:
        return ""

    if isinstance(content, list):
        parts = []
        for segment in content:
            if isinstance(segment, dict):
                seg_text = segment.get("text", "")
                if seg_text:
                    parts.append(seg_text)
            elif isinstance(segment, str):
                parts.append(segment)
        return "\n".join(parts)

    if isinstance(content, str):
        return content

    return ""


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


def unified_tokenize(text: str) -> str:
    """Tokenize text using jieba for Chinese/English FTS."""
    if not text or not text.strip():
        return ""

    normalized = preprocess_for_fts(text)
    words = jieba.lcut(normalized)
    valid_words = [word for word in words if word.strip()]
    return " ".join(valid_words)