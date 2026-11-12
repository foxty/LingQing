"""Unit tests for Chroma vector backend implementations and contract wiring."""

from unittest.mock import MagicMock, patch

import httpx
import pytest
from apps.config import parse_chroma_http_url
from apps.shared.core.exceptions import ValidationError
from tests.stub_embeddings import StubEmbeddings
from apps.shared.infra.rag.chroma_backend import (
    HttpChromaBackend,
    _apply_chroma_http_client_timeout,
    get_vector_backend,
)


def test_parse_chroma_http_url():
    assert parse_chroma_http_url("http://localhost:8002") == ("localhost", 8002, False)
    assert parse_chroma_http_url("http://chroma:8000") == ("chroma", 8000, False)
    assert parse_chroma_http_url("https://chroma.example.com:443") == ("chroma.example.com", 443, True)
    assert parse_chroma_http_url("https://chroma.example.com") == ("chroma.example.com", 443, True)


def test_factory_returns_http_backend(monkeypatch):
    monkeypatch.setattr("apps.shared.infra.rag.chroma_backend.EnvConfig.CHROMA_MODE", "http")

    stub = StubEmbeddings()
    with patch("apps.shared.infra.rag.chroma_backend.HttpChromaBackend") as mock_http_backend:
        backend = get_vector_backend(tenant_id=99, embeddings=stub)

    mock_http_backend.assert_called_once_with(tenant_id=99, embeddings=stub)
    assert backend is mock_http_backend.return_value


def test_get_vector_backend_rejects_missing_embeddings():
    with pytest.raises(ValidationError, match="embedding model profile"):
        get_vector_backend(tenant_id=1, embeddings=None)  # type: ignore[arg-type]


def test_http_backend_init_does_not_construct_http_client():
    """Construction and describe() must not open a Chroma socket."""
    backend = HttpChromaBackend(tenant_id=1, embeddings=StubEmbeddings())
    assert backend._collection is None
    assert backend.describe()["backend"] == "chroma-http"
    assert backend._collection is None


def test_http_backend_builds_client_with_collection(monkeypatch):
    monkeypatch.setattr("apps.shared.infra.rag.chroma_backend.EnvConfig.CHROMA_URL", "http://chroma:8000")
    monkeypatch.setattr("apps.shared.infra.rag.chroma_backend.EnvConfig.CHROMA_COLLECTION_PREFIX", "tenant_")

    mock_collection = MagicMock()
    mock_http_client = MagicMock()
    mock_http_client.get_or_create_collection.return_value = mock_collection

    with patch("apps.shared.infra.rag.chroma_backend.chromadb.HttpClient", return_value=mock_http_client) as mock_ctor:
        backend = HttpChromaBackend(tenant_id=42, embeddings=StubEmbeddings())
        mock_ctor.assert_not_called()
        assert backend.describe()["backend"] == "chroma-http"

        backend._ensure_collection()

        mock_ctor.assert_called_once()
        http_client_call_kwargs = mock_ctor.call_args.kwargs
        assert http_client_call_kwargs["host"] == "chroma"
        assert http_client_call_kwargs["port"] == 8000
        assert http_client_call_kwargs["ssl"] is False
        assert "settings" in http_client_call_kwargs
        get_collection_kwargs = mock_http_client.get_or_create_collection.call_args.kwargs
        assert get_collection_kwargs["name"] == "tenant_42"
        assert get_collection_kwargs["embedding_function"] is not None


@pytest.mark.asyncio
async def test_contract_methods_delegate_to_collection(monkeypatch):
    monkeypatch.setattr("apps.shared.infra.rag.chroma_backend.EnvConfig.CHROMA_COLLECTION_PREFIX", "tenant_")
    monkeypatch.setattr("apps.shared.infra.rag.chroma_backend.EnvConfig.CHROMA_URL", "http://localhost:8000")

    mock_collection = MagicMock()
    mock_collection.query.return_value = {
        "documents": [["ok"]],
        "metadatas": [[{"tenant_id": 1}]],
    }
    mock_collection.get.return_value = {
        "ids": ["id-1"],
        "documents": ["x"],
        "metadatas": [{"tenant_id": 1}],
    }

    mock_http_client = MagicMock()
    mock_http_client.get_or_create_collection.return_value = mock_collection

    with patch("apps.shared.infra.rag.chroma_backend.chromadb.HttpClient", return_value=mock_http_client):
        backend = HttpChromaBackend(tenant_id=1, embeddings=StubEmbeddings())

        records = [{"content": "x", "metadata": {"tenant_id": 1}}]
        await backend.add_records(records)
        search_records = await backend.similarity_search("q", k=3, filter_dict={"tenant_id": 1})
        get_result = await backend.get(where={"tenant_id": 1}, limit=2, include=["metadatas"])
        await backend.delete(where={"tenant_id": 1})
        await backend.delete(ids=["a", "b"])

    mock_collection.add.assert_called_once()
    add_kwargs = mock_collection.add.call_args.kwargs
    assert add_kwargs["documents"] == ["x"]
    assert add_kwargs["metadatas"] == [{"tenant_id": 1}]
    assert len(add_kwargs["ids"]) == 1

    mock_collection.query.assert_called_once_with(
        query_texts=["q"],
        n_results=3,
        include=["documents", "metadatas"],
        where={"tenant_id": 1},
    )
    mock_collection.get.assert_called_once()
    mock_collection.delete.assert_any_call(where={"tenant_id": 1})
    mock_collection.delete.assert_any_call(ids=["a", "b"])
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

    mock_collection = MagicMock()
    mock_http_client = MagicMock()
    mock_http_client.get_or_create_collection.return_value = mock_collection

    with patch("apps.shared.infra.rag.chroma_backend.chromadb.HttpClient", return_value=mock_http_client):
        backend = HttpChromaBackend(tenant_id=123, embeddings=StubEmbeddings())
        await backend.delete_collection()
        assert backend._collection is None

    mock_http_client.delete_collection.assert_called_once_with(name="tenant_123")


@pytest.mark.asyncio
async def test_similarity_search_initializes_collection_off_event_loop(monkeypatch):
    monkeypatch.setattr("apps.shared.infra.rag.chroma_backend.EnvConfig.CHROMA_COLLECTION_PREFIX", "tenant_")
    monkeypatch.setattr("apps.shared.infra.rag.chroma_backend.EnvConfig.CHROMA_URL", "http://localhost:8000")
    monkeypatch.setattr("apps.shared.infra.rag.chroma_backend.EnvConfig.CHROMA_HTTP_TIMEOUT_SECONDS", 60)

    mock_collection = MagicMock()
    mock_collection.query.return_value = {"documents": [[]], "metadatas": [[]]}
    mock_http_client = MagicMock()
    mock_http_client.get_or_create_collection.return_value = mock_collection

    async def run_in_thread(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    with (
        patch("apps.shared.infra.rag.chroma_backend.chromadb.HttpClient", return_value=mock_http_client),
        patch(
            "apps.shared.infra.rag.chroma_backend.asyncio.to_thread",
            side_effect=run_in_thread,
        ) as mock_to_thread,
    ):
        backend = HttpChromaBackend(tenant_id=5, embeddings=StubEmbeddings())
        await backend.similarity_search("query", k=2)

    mock_to_thread.assert_awaited()
    init_calls = [
        c for c in mock_to_thread.await_args_list if c.args and c.args[0] == backend._initialize_collection
    ]
    assert init_calls, "expected _initialize_collection to run via asyncio.to_thread"


def test_apply_chroma_http_client_timeout_patches_httpx_session(monkeypatch):
    monkeypatch.setattr("apps.shared.infra.rag.chroma_backend.EnvConfig.CHROMA_HTTP_TIMEOUT_SECONDS", 45)

    session = httpx.Client(timeout=None)
    server = MagicMock(_session=session)
    client = MagicMock(_server=server)

    _apply_chroma_http_client_timeout(client)

    assert session.timeout.connect == 45.0
    assert session.timeout.read == 45.0
