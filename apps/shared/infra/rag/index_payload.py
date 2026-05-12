"""Pure indexing payload models for the RAG indexing facade."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class IndexRecordPayload:
    """Single indexable record payload."""

    content: str
    metadata: dict[str, Any]


@dataclass(slots=True)
class IndexUpsertPayload:
    """Upsert payload for batch indexing."""

    records: list[IndexRecordPayload]