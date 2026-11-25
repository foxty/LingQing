"""Unit tests for GoogleDriveClient HTTP behavior."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest

from apps.shared.core.exceptions import AuthenticationError, ValidationError
from apps.shared.infra.external_files.google_drive import (
    GOOGLE_MIME_DOCUMENT,
    GOOGLE_MIME_SHORTCUT,
    GOOGLE_TOKEN_URL,
    GoogleDriveClient,
)
from apps.shared.infra.external_files.port import ExternalFileEntry
from apps.shared.infra.oauth import OAuthTokenSet

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


async def test_list_folder_tree_parses_iso8601_modified_time():
    def handler(request: httpx.Request) -> httpx.Response:
        if "/files" in str(request.url) and "alt=media" not in str(request.url):
            return httpx.Response(
                200,
                json={
                    "files": [
                        {
                            "id": "gdoc-1",
                            "name": "Meeting Notes",
                            "mimeType": GOOGLE_MIME_DOCUMENT,
                            "modifiedTime": "2026-09-01T04:46:44.213Z",
                        }
                    ]
                },
            )
        return httpx.Response(404, json={"error": "not found"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        async with GoogleDriveClient(access_token="token", http_client=http_client) as client:
            files = await client.list_folder_tree("root-folder", include_subfolders=False)
    assert len(files) == 1
    assert files[0].modified_at is not None
    assert files[0].modified_at.year == 2026
    assert files[0].modified_at.month == 9


async def test_list_folder_tree_resolves_supported_shortcut_to_target():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/files/doc-target-001"):
            return httpx.Response(
                200,
                json={
                    "id": "doc-target-001",
                    "name": "Team sync notes",
                    "mimeType": GOOGLE_MIME_DOCUMENT,
                    "modifiedTime": "2026-11-10T08:00:00.000Z",
                },
            )
        if "/files" in str(request.url) and "alt=media" not in str(request.url) and "/export" not in str(request.url):
            return httpx.Response(
                200,
                json={
                    "files": [
                        {
                            "id": "shortcut-001",
                            "name": "Team sync notes",
                            "mimeType": GOOGLE_MIME_SHORTCUT,
                            "shortcutDetails": {
                                "targetId": "doc-target-001",
                                "targetMimeType": GOOGLE_MIME_DOCUMENT,
                            },
                        }
                    ]
                },
            )
        return httpx.Response(404, json={"error": "not found"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        async with GoogleDriveClient(access_token="token", http_client=http_client) as client:
            files = await client.list_folder_tree("test-folder-001", include_subfolders=False)

    assert len(files) == 1
    assert files[0].external_id == "doc-target-001"
    assert files[0].mime_type == GOOGLE_MIME_DOCUMENT
    assert files[0].modified_at is not None


async def test_list_folder_tree_skips_shortcut_to_unsupported_target():
    def handler(request: httpx.Request) -> httpx.Response:
        if "/files" in str(request.url) and "alt=media" not in str(request.url) and "/export" not in str(request.url):
            return httpx.Response(
                200,
                json={
                    "files": [
                        {
                            "id": "shortcut-video-001",
                            "name": "Session recording",
                            "mimeType": GOOGLE_MIME_SHORTCUT,
                            "shortcutDetails": {
                                "targetId": "video-target-001",
                                "targetMimeType": "video/mp4",
                            },
                        }
                    ]
                },
            )
        return httpx.Response(404, json={"error": "not found"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        async with GoogleDriveClient(access_token="token", http_client=http_client) as client:
            files = await client.list_folder_tree("test-folder-002", include_subfolders=False)

    assert files == []


async def test_list_folder_tree_dedupes_direct_file_and_shortcut_target():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/files/doc-target-002"):
            return httpx.Response(
                200,
                json={
                    "id": "doc-target-002",
                    "name": "Ops playbook",
                    "mimeType": GOOGLE_MIME_DOCUMENT,
                    "modifiedTime": "2026-11-01T10:00:00.000Z",
                },
            )
        if "/files" in str(request.url) and "alt=media" not in str(request.url) and "/export" not in str(request.url):
            return httpx.Response(
                200,
                json={
                    "files": [
                        {
                            "id": "doc-target-002",
                            "name": "Ops playbook",
                            "mimeType": GOOGLE_MIME_DOCUMENT,
                            "modifiedTime": "2026-11-01T10:00:00.000Z",
                        },
                        {
                            "id": "shortcut-002",
                            "name": "Ops playbook",
                            "mimeType": GOOGLE_MIME_SHORTCUT,
                            "shortcutDetails": {
                                "targetId": "doc-target-002",
                                "targetMimeType": GOOGLE_MIME_DOCUMENT,
                            },
                        },
                    ]
                },
            )
        return httpx.Response(404, json={"error": "not found"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        async with GoogleDriveClient(access_token="token", http_client=http_client) as client:
            files = await client.list_folder_tree("test-folder-003", include_subfolders=False)

    assert len(files) == 1
    assert files[0].external_id == "doc-target-002"


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
    assert captured.get("corpora") == "allDrives"


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
    fake_token_client = AsyncMock()
    fake_token_client.exchange_code = AsyncMock(
        return_value=OAuthTokenSet(
            access_token="access",
            refresh_token="refresh",
            token_type="Bearer",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    tokens = await GoogleDriveClient.exchange_code(
        client_id="cid",
        client_secret="secret",
        redirect_uri="https://app.example/callback",
        code="auth-code",
        code_verifier="verifier",
        token_client=fake_token_client,
    )
    assert tokens.access_token == "access"
    assert tokens.refresh_token == "refresh"
    call_cfg = fake_token_client.exchange_code.await_args.kwargs["config"]
    assert call_cfg.token_url == GOOGLE_TOKEN_URL
    assert call_cfg.client_id == "cid"


async def test_exchange_code_failure_raises():
    fake_token_client = AsyncMock()
    fake_token_client.exchange_code = AsyncMock(side_effect=ValidationError("invalid_grant"))
    with pytest.raises(AuthenticationError):
        await GoogleDriveClient.exchange_code(
            client_id="cid",
            client_secret="secret",
            redirect_uri="https://app.example/callback",
            code="bad-code",
            code_verifier="verifier",
            token_client=fake_token_client,
        )


async def test_refresh_access_token_failure_raises():
    fake_token_client = AsyncMock()
    fake_token_client.refresh = AsyncMock(side_effect=ValidationError("invalid_grant"))
    with pytest.raises(AuthenticationError):
        await GoogleDriveClient.refresh_access_token(
            client_id="cid",
            client_secret="secret",
            refresh_token="bad-refresh",
            token_client=fake_token_client,
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
