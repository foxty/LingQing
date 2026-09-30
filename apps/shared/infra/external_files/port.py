"""Port definitions for external document file providers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class ExternalFileEntry:
    """Normalized external file metadata for sync diffing."""

    external_id: str
    name: str
    mime_type: str
    modified_at: datetime | None
    parent_folder_id: str | None = None


class ExternalFilesClient(Protocol):
    """Client for listing and downloading files from an external source."""

    async def list_folder_tree(self, folder_id: str, *, include_subfolders: bool = True) -> list[ExternalFileEntry]:
        """List supported files under a folder, optionally recursing into subfolders."""
        ...

    async def download_file(self, entry: ExternalFileEntry) -> tuple[str, bytes]:
        """Download or export file content. Returns (filename, content bytes)."""
        ...

    async def get_account_email(self) -> str | None:
        """Return connected account email when available."""
        ...
