"""Unit tests for LangChain ↔ Chroma embedding bridge."""

import numpy as np
from langchain_core.embeddings import Embeddings

from apps.shared.infra.rag.chroma_embedding import LangChainEmbeddingFunction


class _StubEmbeddings(Embeddings):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), 1.0] for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return [float(len(text)), 2.0]


def test_embed_query_returns_ndarray_batch_not_flat_floats():
    fn = LangChainEmbeddingFunction(_StubEmbeddings())
    result = fn.embed_query("alpha")
    assert len(result) == 1
    assert isinstance(result[0], np.ndarray)
    assert result[0].dtype == np.float32
    assert result[0].tolist() == [5.0, 2.0]


def test_call_returns_one_ndarray_per_document():
    fn = LangChainEmbeddingFunction(_StubEmbeddings())
    result = fn(["a", "bb"])
    assert len(result) == 2
    assert all(isinstance(row, np.ndarray) for row in result)
