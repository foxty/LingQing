"""Google Drive client for document sync."""

from __future__ import annotations

import os
from collections import deque
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from apps.config import AppConfig
from apps.shared.core.exceptions import AuthenticationError, ValidationError
from apps.shared.infra.external_files.port import ExternalFileEntry
from apps.shared.infra.oauth import (
    OAuth2TokenClient,
    OAuthTokenClientConfig,
    OAuthTokenSet,
    build_authorize_url,
)
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)

GOOGLE_DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"

GOOGLE_MIME_FOLDER = "application/vnd.google-apps.folder"
GOOGLE_MIME_SHORTCUT = "application/vnd.google-apps.shortcut"
GOOGLE_MIME_DOCUMENT = "application/vnd.google-apps.document"
GOOGLE_MIME_SPREADSHEET = "application/vnd.google-apps.spreadsheet"
GOOGLE_MIME_PRESENTATION = "application/vnd.google-apps.presentation"

GOOGLE_NATIVE_EXPORT_MIMES: dict[str, str] = {
    GOOGLE_MIME_DOCUMENT: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    GOOGLE_MIME_SPREADSHEET: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    GOOGLE_MIME_PRESENTATION: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

EXPORT_EXTENSION_BY_MIME: dict[str, str] = {
    GOOGLE_MIME_DOCUMENT: ".docx",
    GOOGLE_MIME_SPREADSHEET: ".xlsx",
    GOOGLE_MIME_PRESENTATION: ".pptx",
}

MIME_EXTENSION_FALLBACK: dict[str, str] = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.ms-powerpoint": ".ppt",
    "text/html": ".html",
    "text/markdown": ".md",
}


def is_supported_drive_file(name: str, mime_type: str) -> bool:
    """Return True when a Drive file should be synced into LingQing."""
    if mime_type == GOOGLE_MIME_FOLDER:
        return False
    if mime_type in GOOGLE_NATIVE_EXPORT_MIMES:
        return True
    ext = os.path.splitext(name)[1].lower()
    return ext in AppConfig.SUPPORTED_DOCUMENT_EXTENSIONS


def export_filename(name: str, mime_type: str) -> str:
    """Resolve the local filename used after export/download."""
    if mime_type not in GOOGLE_NATIVE_EXPORT_MIMES:
        return name
    base, _ext = os.path.splitext(name)
    export_ext = EXPORT_EXTENSION_BY_MIME[mime_type]
    return f"{base}{export_ext}" if base else f"{name}{export_ext}"


def is_google_native_mime(mime_type: str) -> bool:
    """Return True for Google Docs/Sheets/Slides (exported on download, not stored as binary)."""
    return mime_type in GOOGLE_NATIVE_EXPORT_MIMES


def _parse_drive_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    # Drive API v3 returns ISO 8601 (e.g. 2026-09-01T04:46:44.213Z).
    iso_candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(iso_candidate)
    except ValueError:
        parsed = None
    if parsed is not None:
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _shared_drive_params() -> dict[str, bool]:
    """Query params required for My Drive, Shared with me, and Shared drive items."""
    return {
        "supportsAllDrives": True,
        "includeItemsFromAllDrives": True,
    }


class GoogleDriveClient:
    """Google Drive API client for the connected user's accessible files."""

    def __init__(
        self,
        *,
        access_token: str,
        http_client: httpx.AsyncClient | None = None,
    ):
        if not access_token:
            raise ValidationError("Google Drive access token is required")
        self._access_token = access_token
        self._http_client = http_client
        self._owns_client = http_client is None

    async def __aenter__(self) -> GoogleDriveClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=60.0)
            self._owns_client = True
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._owns_client and self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    @property
    def _client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            raise RuntimeError("GoogleDriveClient must be used as an async context manager")
        return self._http_client

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._access_token}"}

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        follow_redirects: bool = True,
    ) -> httpx.Response:
        response = await self._client.request(
            method,
            url,
            params=params,
            headers=self._headers(),
            follow_redirects=follow_redirects,
        )
        if response.status_code == 401:
            raise AuthenticationError(
                "Google Drive credentials expired or invalid",
                {"code": "DRIVE_AUTH_EXPIRED"},
            )
        if response.status_code >= 400:
            logger.warning(
                "google_drive_api_error method=%s url=%s status=%s body=%s",
                method,
                url,
                response.status_code,
                response.text[:500],
            )
            raise ValidationError(f"Google Drive API error: {response.status_code}")
        return response

    async def get_account_email(self) -> str | None:
        response = await self._request(
            "GET",
            f"{GOOGLE_DRIVE_API_BASE}/about",
            params={"fields": "user(emailAddress)"},
        )
        user = response.json().get("user") or {}
        return user.get("emailAddress")

    async def _get_file_metadata(self, file_id: str) -> dict[str, Any]:
        response = await self._request(
            "GET",
            f"{GOOGLE_DRIVE_API_BASE}/files/{file_id}",
            params={"fields": "id,name,mimeType,modifiedTime", **_shared_drive_params()},
        )
        return response.json()

    async def _entry_from_shortcut(
        self,
        item: dict[str, Any],
        *,
        parent_folder_id: str,
        target_metadata_cache: dict[str, dict[str, Any]],
    ) -> ExternalFileEntry | None:
        """Resolve a Drive shortcut to a supported target file entry."""
        shortcut_details = item.get("shortcutDetails") or {}
        target_id = shortcut_details.get("targetId")
        target_mime = shortcut_details.get("targetMimeType") or ""
        shortcut_name = item.get("name", "")
        if not target_id:
            return None
        if not is_supported_drive_file(shortcut_name, target_mime):
            return None
        if target_id not in target_metadata_cache:
            target_metadata_cache[target_id] = await self._get_file_metadata(target_id)
        target = target_metadata_cache[target_id]
        target_name = target.get("name") or shortcut_name
        target_mime = target.get("mimeType") or target_mime
        if not is_supported_drive_file(target_name, target_mime):
            return None
        return ExternalFileEntry(
            external_id=target_id,
            name=target_name,
            mime_type=target_mime,
            modified_at=_parse_drive_timestamp(target.get("modifiedTime")),
            parent_folder_id=parent_folder_id,
        )

    async def list_folder_tree(self, folder_id: str, *, include_subfolders: bool = True) -> list[ExternalFileEntry]:
        """Walk folder and return supported files, optionally recursing into subfolders."""
        entries_by_id: dict[str, ExternalFileEntry] = {}
        folder_queue: deque[str] = deque([folder_id])
        target_metadata_cache: dict[str, dict[str, Any]] = {}

        while folder_queue:
            current_folder = folder_queue.popleft()
            page_token: str | None = None
            while True:
                params: dict[str, Any] = {
                    "q": f"'{current_folder}' in parents and trashed = false",
                    "fields": ("nextPageToken,files(id,name,mimeType,modifiedTime,parents,shortcutDetails)"),
                    "pageSize": 200,
                    # Required so shared / team folders (not only My Drive) return children.
                    "corpora": "allDrives",
                    **_shared_drive_params(),
                }
                if page_token:
                    params["pageToken"] = page_token

                response = await self._request("GET", f"{GOOGLE_DRIVE_API_BASE}/files", params=params)
                payload = response.json()
                for item in payload.get("files", []):
                    mime_type = item.get("mimeType", "")
                    name = item.get("name", "")
                    if mime_type == GOOGLE_MIME_FOLDER:
                        if include_subfolders:
                            folder_queue.append(item["id"])
                        continue
                    if mime_type == GOOGLE_MIME_SHORTCUT:
                        entry = await self._entry_from_shortcut(
                            item,
                            parent_folder_id=current_folder,
                            target_metadata_cache=target_metadata_cache,
                        )
                        if entry is not None:
                            entries_by_id[entry.external_id] = entry
                        continue
                    if not is_supported_drive_file(name, mime_type):
                        continue
                    entries_by_id[item["id"]] = ExternalFileEntry(
                        external_id=item["id"],
                        name=name,
                        mime_type=mime_type,
                        modified_at=_parse_drive_timestamp(item.get("modifiedTime")),
                        parent_folder_id=current_folder,
                    )
                page_token = payload.get("nextPageToken")
                if not page_token:
                    break

        return list(entries_by_id.values())

    async def download_file(self, entry: ExternalFileEntry) -> tuple[str, bytes]:
        filename = export_filename(entry.name, entry.mime_type)
        if entry.mime_type in GOOGLE_NATIVE_EXPORT_MIMES:
            export_mime = GOOGLE_NATIVE_EXPORT_MIMES[entry.mime_type]
            response = await self._request(
                "GET",
                f"{GOOGLE_DRIVE_API_BASE}/files/{entry.external_id}/export",
                params={"mimeType": export_mime, **_shared_drive_params()},
                follow_redirects=True,
            )
            return filename, response.content

        response = await self._request(
            "GET",
            f"{GOOGLE_DRIVE_API_BASE}/files/{entry.external_id}",
            params={"alt": "media", **_shared_drive_params()},
            follow_redirects=True,
        )
        return filename, response.content

    @staticmethod
    def build_authorize_url(
        *,
        client_id: str,
        redirect_uri: str,
        state: str,
        code_challenge: str,
    ) -> str:
        return build_authorize_url(
            GOOGLE_AUTHORIZE_URL,
            client_id=client_id,
            redirect_uri=redirect_uri,
            state=state,
            code_challenge=code_challenge,
            scopes=[GOOGLE_DRIVE_SCOPE],
            extra_params={
                "access_type": "offline",
                "prompt": "consent",
            },
        )

    @staticmethod
    async def exchange_code(
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        code: str,
        code_verifier: str,
        token_client: OAuth2TokenClient | None = None,
    ) -> OAuthTokenSet:
        client = token_client or OAuth2TokenClient()
        try:
            return await client.exchange_code(
                config=OAuthTokenClientConfig(
                    token_url=GOOGLE_TOKEN_URL,
                    client_id=client_id,
                    client_secret=client_secret,
                ),
                code=code,
                code_verifier=code_verifier,
                redirect_uri=redirect_uri,
            )
        except ValidationError as exc:
            logger.warning("google_drive_token_exchange_failed error=%s", exc)
            raise AuthenticationError(
                "Google Drive token exchange failed",
                {"code": "DRIVE_TOKEN_EXCHANGE_FAILED"},
            ) from exc

    @staticmethod
    async def refresh_access_token(
        *,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        token_client: OAuth2TokenClient | None = None,
    ) -> OAuthTokenSet:
        client = token_client or OAuth2TokenClient()
        try:
            return await client.refresh(
                config=OAuthTokenClientConfig(
                    token_url=GOOGLE_TOKEN_URL,
                    client_id=client_id,
                    client_secret=client_secret,
                ),
                refresh_token=refresh_token,
            )
        except ValidationError as exc:
            logger.warning("google_drive_token_refresh_failed error=%s", exc)
            raise AuthenticationError(
                "Google Drive token refresh failed",
                {"code": "DRIVE_TOKEN_REFRESH_FAILED"},
            ) from exc
