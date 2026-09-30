"""Unit tests for GoogleDriveClient HTTP behavior."""

from __future__ import annotations

import httpx
import pytest

from apps.shared.core.exceptions import AuthenticationError
from apps.shared.infra.external_files.google_drive import GOOGLE_MIME_DOCUMENT, GoogleDriveClient
from apps.shared.infra.external_files.port import ExternalFileEntry

pytestmark = pytest.mark.asyncio


def _mock_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/about" in url:
            return httpx.Response(200, json={"user": {"emailAddress": "drive-user@test-sync.example"}})
        if "/files" in url and "alt=media" not in url and "/export" not in url:
            return httpx.Response(
                200,
                json={
                    "files": [
                        {
                            "id": "file-1",
                            "name": "notes.pdf",
                            "mimeType": "application/pdf",
                            "modifiedTime": "Mon, 01 Jan 2026 00:00:00 GMT",
                        }
                    ]
                },
            )
        if "/export" in url:
            return httpx.Response(200, content=b"docx-bytes")
        if "alt=media" in url:
            return httpx.Response(200, content=b"pdf-bytes")
        if "oauth2.googleapis.com/token" in url:
            return httpx.Response(200, json={"access_token": "new-access", "expires_in": 3600})
        return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(handler)


async def test_get_account_email():
    async with httpx.AsyncClient(transport=_mock_transport()) as http_client:
        async with GoogleDriveClient(access_token="token", http_client=http_client) as client:
            email = await client.get_account_email()
    assert email == "drive-user@test-sync.example"


async def test_list_folder_tree_returns_supported_files():
    async with httpx.AsyncClient(transport=_mock_transport()) as http_client:
        async with GoogleDriveClient(access_token="token", http_client=http_client) as client:
            files = await client.list_folder_tree("root-folder", include_subfolders=False)
    assert len(files) == 1
    assert files[0].external_id == "file-1"
    assert files[0].name == "notes.pdf"


async def test_list_folder_tree_includes_shared_drive_params():
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/files" in url and "alt=media" not in url and "/export" not in url:
            captured.update(dict(request.url.params))
            return httpx.Response(200, json={"files": []})
        return httpx.Response(404, json={"error": "not found"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        async with GoogleDriveClient(access_token="token", http_client=http_client) as client:
            await client.list_folder_tree("shared-folder-id", include_subfolders=False)

    assert captured.get("supportsAllDrives") == "true"
    assert captured.get("includeItemsFromAllDrives") == "true"


async def test_download_file_includes_shared_drive_params():
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(dict(request.url.params))
        if "/export" in str(request.url):
            return httpx.Response(200, content=b"docx-bytes")
        if "alt=media" in str(request.url):
            return httpx.Response(200, content=b"pdf-bytes")
        return httpx.Response(404, json={"error": "not found"})

    entry = ExternalFileEntry(
        external_id="file-1",
        name="notes.pdf",
        mime_type="application/pdf",
        modified_at=None,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        async with GoogleDriveClient(access_token="token", http_client=http_client) as client:
            await client.download_file(entry)

    assert captured.get("supportsAllDrives") == "true"
    assert captured.get("includeItemsFromAllDrives") == "true"


async def test_download_file_binary():
    entry = ExternalFileEntry(
        external_id="file-1",
        name="notes.pdf",
        mime_type="application/pdf",
        modified_at=None,
    )
    async with httpx.AsyncClient(transport=_mock_transport()) as http_client:
        async with GoogleDriveClient(access_token="token", http_client=http_client) as client:
            filename, content = await client.download_file(entry)
    assert filename == "notes.pdf"
    assert content == b"pdf-bytes"


async def test_download_file_google_native_export():
    entry = ExternalFileEntry(
        external_id="gdoc-1",
        name="Plan",
        mime_type=GOOGLE_MIME_DOCUMENT,
        modified_at=None,
    )
    async with httpx.AsyncClient(transport=_mock_transport()) as http_client:
        async with GoogleDriveClient(access_token="token", http_client=http_client) as client:
            filename, content = await client.download_file(entry)
    assert filename == "Plan.docx"
    assert content == b"docx-bytes"


async def test_exchange_code_success():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={"access_token": "access", "refresh_token": "refresh", "expires_in": 3600},
        )
    )
    async with httpx.AsyncClient(transport=transport) as http_client:
        payload = await GoogleDriveClient.exchange_code(
            client_id="cid",
            client_secret="secret",
            redirect_uri="https://app.example/callback",
            code="auth-code",
            code_verifier="verifier",
            http_client=http_client,
        )
    assert payload["access_token"] == "access"
    assert payload["refresh_token"] == "refresh"


async def test_exchange_code_failure_raises():
    transport = httpx.MockTransport(lambda request: httpx.Response(400, json={"error": "invalid_grant"}))
    async with httpx.AsyncClient(transport=transport) as http_client:
        with pytest.raises(AuthenticationError):
            await GoogleDriveClient.exchange_code(
                client_id="cid",
                client_secret="secret",
                redirect_uri="https://app.example/callback",
                code="bad-code",
                code_verifier="verifier",
                http_client=http_client,
            )


async def test_build_authorize_url_contains_pkce_params():
    url = GoogleDriveClient.build_authorize_url(
        client_id="cid",
        redirect_uri="https://app.example/callback",
        state="state-1",
        code_challenge="challenge",
    )
    assert "client_id=cid" in url
    assert "state=state-1" in url
    assert "code_challenge=challenge" in url
