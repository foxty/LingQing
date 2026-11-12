"""Minimal Embeddings stub for unit and integration tests."""

from langchain_core.embeddings import Embeddings


class StubEmbeddings(Embeddings):
    """Fixed-size deterministic vectors for tests."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3]
