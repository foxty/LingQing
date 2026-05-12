"""Unit tests for Chroma vector backend implementations and contract wiring."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.documents import Document

from apps.config import parse_chroma_http_url
from apps.shared.infra.rag.chroma_backend import (
    HttpChromaBackend,
    get_vector_backend,
)


def test_parse_chroma_http_url():
    assert parse_chroma_http_url("http://localhost:8002") == ("localhost", 8002, False)
    assert parse_chroma_http_url("http://chroma:8000") == ("chroma", 8000, False)
    assert parse_chroma_http_url("https://chroma.example.com:443") == ("chroma.example.com", 443, True)
    assert parse_chroma_http_url("https://chroma.example.com") == ("chroma.example.com", 443, True)


def test_factory_returns_http_backend(monkeypatch):
    monkeypatch.setattr("apps.shared.infra.rag.chroma_backend.EnvConfig.CHROMA_MODE", "http")

    with patch("apps.shared.infra.rag.chroma_backend.HttpChromaBackend") as mock_http_backend:
        backend = get_vector_backend(tenant_id=99)

    mock_http_backend.assert_called_once_with(tenant_id=99, embeddings=None)
    assert backend is mock_http_backend.return_value


def test_http_backend_init_does_not_construct_http_client():
    """Construction and describe() must not open a Chroma socket."""
    backend = HttpChromaBackend(tenant_id=1)
    assert backend._vectorstore is None
    assert backend.describe()["backend"] == "chroma-http"
    assert backend._vectorstore is None


def test_http_backend_builds_client_with_collection(monkeypatch):
    monkeypatch.setattr("apps.shared.infra.rag.chroma_backend.EnvConfig.CHROMA_URL", "http://chroma:8000")
    monkeypatch.setattr("apps.shared.infra.rag.chroma_backend.EnvConfig.CHROMA_COLLECTION_PREFIX", "tenant_")

    with (
        patch("apps.shared.infra.rag.chroma_backend.chromadb.HttpClient") as mock_http_client,
        patch("apps.shared.infra.rag.chroma_backend.Chroma") as mock_chroma,
    ):
        backend = HttpChromaBackend(tenant_id=42)
        mock_http_client.assert_not_called()
        mock_chroma.assert_not_called()
        assert backend.describe()["backend"] == "chroma-http"
        mock_http_client.assert_not_called()

        backend._ensure_vectorstore()

        mock_http_client.assert_called_once()
        http_client_call_kwargs = mock_http_client.call_args.kwargs
        assert http_client_call_kwargs["host"] == "chroma"
        assert http_client_call_kwargs["port"] == 8000
        assert http_client_call_kwargs["ssl"] is False
        assert "settings" in http_client_call_kwargs
        assert http_client_call_kwargs["settings"] is not None
        call_kwargs = mock_chroma.call_args[1]
        assert call_kwargs["client"] is mock_http_client.return_value
        assert call_kwargs["collection_name"] == "tenant_42"


@pytest.mark.asyncio
async def test_contract_methods_delegate_to_vectorstore(monkeypatch):
    monkeypatch.setattr("apps.shared.infra.rag.chroma_backend.EnvConfig.CHROMA_COLLECTION_PREFIX", "tenant_")
    monkeypatch.setattr("apps.shared.infra.rag.chroma_backend.EnvConfig.CHROMA_URL", "http://localhost:8000")

    mock_vs = MagicMock()
    mock_vs.aadd_documents = AsyncMock()
    mock_vs.asimilarity_search = AsyncMock(return_value=[Document(page_content="ok", metadata={"tenant_id": 1})])
    mock_vs.get = MagicMock(return_value={"documents": ["x"], "metadatas": [{"tenant_id": 1}], "ids": ["id-1"]})
    mock_vs.delete = MagicMock()
    mock_vs.adelete = AsyncMock()

    mock_http_client = MagicMock()

    with (
        patch("apps.shared.infra.rag.chroma_backend.chromadb.HttpClient", return_value=mock_http_client),
        patch("apps.shared.infra.rag.chroma_backend.Chroma", return_value=mock_vs),
    ):
        backend = HttpChromaBackend(tenant_id=1)

        records = [{"content": "x", "metadata": {"tenant_id": 1}}]
        await backend.add_records(records)
        search_records = await backend.similarity_search("q", k=3, filter_dict={"tenant_id": 1})
        get_result = await backend.get(where={"tenant_id": 1}, limit=2, include=["metadatas"])
        await backend.delete(where={"tenant_id": 1})
        await backend.delete(ids=["a", "b"])

    mock_vs.aadd_documents.assert_called_once()
    mock_vs.asimilarity_search.assert_called_once_with("q", k=3, filter={"tenant_id": 1})
    mock_vs.get.assert_called_once()
    mock_vs.delete.assert_called_once_with(where={"tenant_id": 1})
    mock_vs.adelete.assert_called_once_with(ids=["a", "b"])
    assert search_records == [{"content": "ok", "metadata": {"tenant_id": 1}}]
    assert get_result == {
        "ids": ["id-1"],
        "records": [{"content": "x", "metadata": {"tenant_id": 1}}],
    }


@pytest.mark.asyncio
async def test_delete_collection_delegates_to_client(monkeypatch):
    """Test delete_collection calls client.delete_collection with correct name."""
    monkeypatch.setattr("apps.shared.infra.rag.chroma_backend.EnvConfig.CHROMA_COLLECTION_PREFIX", "tenant_")
    monkeypatch.setattr("apps.shared.infra.rag.chroma_backend.EnvConfig.CHROMA_URL", "http://localhost:8000")

    mock_vs = MagicMock()
    mock_vs._client = MagicMock()
    mock_vs._client.delete_collection = MagicMock()

    mock_http_client = MagicMock()

    with (
        patch("apps.shared.infra.rag.chroma_backend.chromadb.HttpClient", return_value=mock_http_client),
        patch("apps.shared.infra.rag.chroma_backend.Chroma", return_value=mock_vs),
    ):
        backend = HttpChromaBackend(tenant_id=123)
        await backend.delete_collection()
        assert backend._vectorstore is None

    mock_vs._client.delete_collection.assert_called_once_with(name="tenant_123")
