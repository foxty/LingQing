"""Google Drive client for document sync."""

from __future__ import annotations

import os
from collections import deque
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlencode

import httpx

from apps.config import AppConfig
from apps.shared.core.exceptions import AuthenticationError, ValidationError
from apps.shared.infra.external_files.port import ExternalFileEntry
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)

GOOGLE_DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"

GOOGLE_MIME_FOLDER = "application/vnd.google-apps.folder"
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


def _parse_drive_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
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

    async def list_folder_tree(self, folder_id: str, *, include_subfolders: bool = True) -> list[ExternalFileEntry]:
        """Walk folder and return supported files, optionally recursing into subfolders."""
        files: list[ExternalFileEntry] = []
        folder_queue: deque[str] = deque([folder_id])

        while folder_queue:
            current_folder = folder_queue.popleft()
            page_token: str | None = None
            while True:
                params: dict[str, Any] = {
                    "q": f"'{current_folder}' in parents and trashed = false",
                    "fields": "nextPageToken,files(id,name,mimeType,modifiedTime,parents)",
                    "pageSize": 200,
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
                    if not is_supported_drive_file(name, mime_type):
                        continue
                    files.append(
                        ExternalFileEntry(
                            external_id=item["id"],
                            name=name,
                            mime_type=mime_type,
                            modified_at=_parse_drive_timestamp(item.get("modifiedTime")),
                            parent_folder_id=current_folder,
                        )
                    )
                page_token = payload.get("nextPageToken")
                if not page_token:
                    break

        return files

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
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": GOOGLE_DRIVE_SCOPE,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "access_type": "offline",
            "prompt": "consent",
        }
        return f"{GOOGLE_AUTHORIZE_URL}?{urlencode(params)}"

    @staticmethod
    async def exchange_code(
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        code: str,
        code_verifier: str,
        http_client: httpx.AsyncClient,
    ) -> dict[str, Any]:
        response = await http_client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": code_verifier,
            },
            timeout=30.0,
        )
        if response.status_code != 200:
            logger.warning(
                "google_drive_token_exchange_failed status=%s body=%s", response.status_code, response.text[:500]
            )
            raise AuthenticationError(
                "Google Drive token exchange failed",
                {"code": "DRIVE_TOKEN_EXCHANGE_FAILED"},
            )
        return response.json()

    @staticmethod
    async def refresh_access_token(
        *,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        http_client: httpx.AsyncClient,
    ) -> dict[str, Any]:
        response = await http_client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=30.0,
        )
        if response.status_code != 200:
            logger.warning(
                "google_drive_token_refresh_failed status=%s body=%s", response.status_code, response.text[:500]
            )
            raise AuthenticationError(
                "Google Drive token refresh failed",
                {"code": "DRIVE_TOKEN_REFRESH_FAILED"},
            )
        return response.json()
