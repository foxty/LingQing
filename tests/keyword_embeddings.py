"""Deterministic keyword-count embeddings for integration tests (not production)."""

from langchain_core.embeddings import Embeddings


class KeywordEmbeddings(Embeddings):
    """Maps text to a small vector of keyword occurrence counts."""

    _keywords = [
        "alpha",
        "beta",
        "tenant1",
        "tenant2",
        "document",
        "asset",
        "shared",
        "lookup",
        "order",
        "customer",
        # Search integration smoke fixture query terms (wiring only, not semantic quality)
        "account",
        "billing",
        "checklist",
        "incident",
        "invoice",
        "on-call",
        "payment",
        "pipeline",
        "planning",
        "playbook",
        "refund",
        "retries",
        "runbook",
        "sales",
        "strategy",
    ]

    def _encode(self, text: str) -> list[float]:
        lowered = text.lower()
        return [float(lowered.count(keyword)) for keyword in self._keywords]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._encode(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._encode(text)
