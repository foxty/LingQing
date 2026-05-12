"""Unit tests for OpenAPI source URL adapter and schema resolver error messages."""

from __future__ import annotations

import pytest

from apps.shared.api_connector.schema_parser import SchemaSourceResolver
from apps.shared.api_connector.source_url_adapter import OpenApiSourceUrlAdapter
from apps.shared.core.exceptions import ValidationError


def test_github_blob_url_is_adapted_to_raw_url():
    result = OpenApiSourceUrlAdapter.adapt(
        "https://github.com/github/rest-api-description/blob/main/descriptions/api.github.com/api.github.com.yaml"
    )
    assert result.adapted is True
    assert result.reason == "github-blob-to-raw"
    assert result.url == (
        "https://raw.githubusercontent.com/github/rest-api-description/main/"
        "descriptions/api.github.com/api.github.com.yaml"
    )


@pytest.mark.asyncio
async def test_openapi_url_returns_clear_error_when_payload_is_html(monkeypatch):
    class _FakeResponse:
        status = 200
        headers = {"Content-Type": "text/html; charset=utf-8"}

        async def text(self):
            return "<!doctype html><html><body>Not Raw</body></html>"

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _FakeSession:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, url):
            return _FakeResponse()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("apps.shared.api_connector.schema_parser.aiohttp.ClientSession", _FakeSession)

    with pytest.raises(ValidationError, match="HTML page"):
        await SchemaSourceResolver.resolve(
            source_type="openapi_url",
            source_url="https://github.com/org/repo/blob/main/openapi.yaml",
        )
