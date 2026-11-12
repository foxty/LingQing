"""Bridge LangChain embedding clients to Chroma's EmbeddingFunction protocol."""

from __future__ import annotations

from typing import cast

import numpy as np
from chromadb.api.types import Documents, EmbeddingFunction
from chromadb.api.types import Embeddings as ChromaEmbeddings
from langchain_core.embeddings import Embeddings


def _coerce_documents(input: Documents | str) -> list[str]:
    if isinstance(input, str):
        return [input]
    return list(input)


class LangChainEmbeddingFunction(EmbeddingFunction[Documents]):
    """Wrap a LangChain ``Embeddings`` instance for native Chroma collections."""

    def __init__(self, embeddings: Embeddings) -> None:
        self._embeddings = embeddings

    def __call__(self, input: Documents) -> ChromaEmbeddings:
        texts = _coerce_documents(input)
        if not texts:
            return []
        vectors = self._embeddings.embed_documents(texts)
        return cast(ChromaEmbeddings, [np.array(vector, dtype=np.float32) for vector in vectors])

    def embed_query(self, input: Documents | str) -> ChromaEmbeddings:
        """Query path must return one ndarray per query text, not a bare float vector."""
        texts = _coerce_documents(input)
        return cast(
            ChromaEmbeddings,
            [np.array(self._embeddings.embed_query(text), dtype=np.float32) for text in texts],
        )
