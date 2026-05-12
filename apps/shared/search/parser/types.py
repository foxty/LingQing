"""Parser result types."""

from __future__ import annotations

from dataclasses import dataclass, field

from langchain_core.documents import Document


@dataclass
class ParseResult:
    """Standardized output from Flow 2 (sync job)."""

    tokenized_content: str
    chunks: list[Document] = field(default_factory=list)
