"""Parsed document artifact layout and manifest pointer helpers."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from apps.config import get_tenant_documents_path
from apps.shared.document.types import (
    BlocksDocument,
    DocumentBlock,
    ManifestPointer,
)
from apps.shared.infra.storage import FileStorage
from apps.shared.infra.storage.paths import normalize_storage_key, resolve_storage_ref
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class DecodedImage:
    content: bytes
    extension: str


BLOCK_SCHEMA_VERSION = 1
MANIFEST_SCHEMA_VERSION = 1
INDEXABLE_BLOCK_TYPES = frozenset({"text", "heading", "table", "image"})

BLOCKS_RELATIVE_KEY = "parsed/latest/blocks.json"
_MAX_IMAGE_BYTES = 8 * 1024 * 1024
_IMAGE_FILENAME = re.compile(r"^[a-f0-9]{64}\.(png|jpg|jpeg|gif|webp|bmp|tif|tiff)$")
_MIME_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/tiff": ".tif",
}
_EXTENSION_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}


def blocks_relative_key(document_id: int) -> str:
    return f"{document_id}/{BLOCKS_RELATIVE_KEY}"


def document_image_relative_key(document_id: int, filename: str) -> str | None:
    """Tenant-relative key for one stored parse image, or None if the name is unsafe."""
    if not _IMAGE_FILENAME.fullmatch(filename):
        return None
    return f"{document_id}/parsed/latest/images/{filename}"


def image_media_type(filename: str) -> str | None:
    return _EXTENSION_MEDIA_TYPES.get(Path(filename).suffix.lower())


def summarize_blocks(blocks: list[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for block in blocks:
        block_type = block.get("type", "text")
        summary[block_type] = summary.get(block_type, 0) + 1
    return summary


def build_blocks_document(*, parser: str, blocks: list[dict[str, Any]]) -> BlocksDocument:
    return {
        "schema_version": BLOCK_SCHEMA_VERSION,
        "parser": parser,
        "blocks": blocks,  # type: ignore[typeddict-item]
    }


def build_manifest_pointer(
    *,
    storage_uri: str,
    content_hash: str,
    block_summary: dict[str, int],
    filename: str,
    parser: str,
) -> ManifestPointer:
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "storage_uri": storage_uri,
        "content_hash": content_hash,
        "block_summary": block_summary,
        "meta": {"filename": filename, "parser": parser},
    }


def is_manifest_pointer(raw_content: dict | None) -> bool:
    if not raw_content or not isinstance(raw_content, dict):
        return False
    return bool(raw_content.get("storage_uri")) and raw_content.get("schema_version") == MANIFEST_SCHEMA_VERSION


def get_storage_uri(raw_content: dict | None) -> str | None:
    if not raw_content:
        return None
    storage_uri = raw_content.get("storage_uri")
    return storage_uri if isinstance(storage_uri, str) and storage_uri else None


def compute_content_hash(blocks_document: BlocksDocument | dict[str, Any]) -> str:
    payload = json.dumps(blocks_document, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def extract_text_from_blocks(blocks_document: BlocksDocument | dict[str, Any]) -> str:
    parts: list[str] = []
    for block in blocks_document.get("blocks", []):
        if not isinstance(block, dict):
            continue
        if block.get("type") not in INDEXABLE_BLOCK_TYPES:
            continue
        text = block.get("text")
        if isinstance(text, str) and text.strip():
            parts.append(text.strip())
    return "\n\n".join(parts)


def text_to_blocks(text: str, *, page: int | None = None) -> list[dict[str, Any]]:
    if not text or not text.strip():
        return []
    block: dict[str, Any] = {"type": "text", "text": text.strip()}
    if page is not None:
        block["page"] = page
    return [block]


async def persist_parse_images(
    file_storage: FileStorage,
    *,
    tenant_id: int,
    document_id: int,
    blocks: list[DocumentBlock],
) -> list[DocumentBlock]:
    """Write image bytes beside blocks.json and rewrite image block URIs to storage keys."""
    persisted: list[DocumentBlock] = []
    for block in blocks:
        if not isinstance(block, dict) or block.get("type") != "image":
            persisted.append(block)
            continue
        stored = await _store_image_block(file_storage, tenant_id=tenant_id, document_id=document_id, block=block)
        if stored is not None:
            persisted.append(stored)
    return persisted


async def _store_image_block(
    file_storage: FileStorage,
    *,
    tenant_id: int,
    document_id: int,
    block: DocumentBlock,
) -> DocumentBlock | None:
    uri = block.get("uri")
    if not isinstance(uri, str) or not uri.strip():
        return None
    uri = uri.strip()
    existing_name = Path(uri.replace("\\", "/")).name
    existing_key = document_image_relative_key(document_id, existing_name)
    if existing_key and (uri.replace("\\", "/") == existing_key or uri.replace("\\", "/").endswith("/" + existing_key)):
        return {**block, "uri": existing_key}

    decoded = _decode_image_bytes(uri)
    if decoded is None:
        logger.warning(
            "Skipping unreadable parse image tenant_id=%s document_id=%s",
            tenant_id,
            document_id,
        )
        return None
    filename = f"{hashlib.sha256(decoded.content).hexdigest()}{decoded.extension}"
    relative_key = document_image_relative_key(document_id, filename)
    if relative_key is None:
        return None
    await file_storage.save(str(tenant_id), relative_key, BytesIO(decoded.content))
    return {**block, "uri": relative_key}


def _decode_image_bytes(uri: str) -> DecodedImage | None:
    if uri.startswith("data:image/"):
        header, separator, payload = uri.partition(",")
        if not separator or ";base64" not in header:
            return None
        mime = header[5:].split(";", 1)[0].lower()
        extension = _MIME_EXTENSIONS.get(mime)
        if extension is None:
            return None
        try:
            raw = base64.b64decode(payload, validate=True)
        except Exception:
            return None
        if not raw or len(raw) > _MAX_IMAGE_BYTES:
            return None
        return DecodedImage(raw, extension)

    path = Path(uri)
    extension = _EXTENSION_MEDIA_TYPES.get(path.suffix.lower())
    if extension is None or not path.is_file():
        return None
    raw = path.read_bytes()
    if not raw or len(raw) > _MAX_IMAGE_BYTES:
        return None
    return DecodedImage(raw, path.suffix.lower())


async def write_blocks_json(
    file_storage: FileStorage,
    *,
    tenant_id: int,
    document_id: int,
    blocks_document: BlocksDocument | dict[str, Any],
) -> str:
    relative_key = blocks_relative_key(document_id)
    payload = json.dumps(blocks_document, ensure_ascii=False).encode("utf-8")
    storage_key = await file_storage.save(str(tenant_id), relative_key, BytesIO(payload))
    return normalize_storage_key(tenant_id, storage_key)


async def try_read_existing_blocks(
    file_storage: FileStorage,
    *,
    tenant_id: int,
    document_id: int,
) -> BlocksDocument | None:
    """Return on-disk blocks.json when present; None if missing or unreadable."""
    relative_key = blocks_relative_key(document_id)
    resolved = resolve_storage_ref(tenant_id, relative_key)
    try:
        if not await file_storage.exists(resolved):
            return None
        return await read_blocks_json(file_storage, relative_key, tenant_id=tenant_id)
    except Exception as exc:
        logger.warning(
            "Failed to read existing parse artifacts tenant_id=%s document_id=%s error=%s",
            tenant_id,
            document_id,
            exc,
        )
        return None


async def read_blocks_json(
    file_storage: FileStorage,
    storage_uri: str,
    *,
    tenant_id: int,
) -> BlocksDocument:
    resolved = resolve_storage_ref(tenant_id, storage_uri)
    raw = await file_storage.read(resolved)
    document = json.loads(raw.decode("utf-8"))
    if not isinstance(document, dict):
        raise ValueError("blocks.json must be a JSON object")
    return document  # type: ignore[return-value]


async def delete_parsed_artifacts(
    file_storage: FileStorage,
    *,
    tenant_id: int,
    document_id: int,
    storage_uri: str | None = None,
) -> None:
    candidate_paths: list[str] = []
    if storage_uri:
        candidate_paths.append(storage_uri)
        candidate_paths.append(resolve_storage_ref(tenant_id, storage_uri))
    default_blocks_key = blocks_relative_key(document_id)
    candidate_paths.append(default_blocks_key)
    candidate_paths.append(resolve_storage_ref(tenant_id, default_blocks_key))

    seen: set[str] = set()
    for path in candidate_paths:
        if not path or path in seen:
            continue
        seen.add(path)
        try:
            resolved = (
                path if path.startswith("s3://") or Path(path).is_absolute() else resolve_storage_ref(tenant_id, path)
            )
            if await file_storage.exists(resolved):
                await _delete_referenced_images(
                    file_storage, tenant_id=tenant_id, document_id=document_id, resolved=resolved
                )
                await file_storage.delete(resolved)
                logger.info("Deleted parsed artifact: %s", resolved)
        except Exception as exc:
            logger.warning("Failed to delete parsed artifact %s: %s", path, exc)

    doc_artifact_dir = Path(get_tenant_documents_path(tenant_id)) / str(document_id)
    if doc_artifact_dir.exists():
        try:
            shutil.rmtree(doc_artifact_dir)
            logger.info("Deleted document artifact directory: %s", doc_artifact_dir)
        except Exception as exc:
            logger.warning("Failed to delete document artifact directory %s: %s", doc_artifact_dir, exc)


async def _delete_referenced_images(
    file_storage: FileStorage,
    *,
    tenant_id: int,
    document_id: int,
    resolved: str,
) -> None:
    try:
        document = json.loads((await file_storage.read(resolved)).decode("utf-8"))
    except Exception:
        return
    if not isinstance(document, dict):
        return
    for block in document.get("blocks", []):
        if not isinstance(block, dict) or block.get("type") != "image":
            continue
        uri = block.get("uri")
        if not isinstance(uri, str):
            continue
        key = document_image_relative_key(document_id, Path(uri).name)
        if key is None:
            continue
        image_ref = uri if uri.startswith("s3://") else resolve_storage_ref(tenant_id, key)
        try:
            if await file_storage.exists(image_ref):
                await file_storage.delete(image_ref)
        except Exception as exc:
            logger.warning("Failed to delete parse image %s: %s", image_ref, exc)


__all__ = [
    "BLOCKS_RELATIVE_KEY",
    "BLOCK_SCHEMA_VERSION",
    "INDEXABLE_BLOCK_TYPES",
    "MANIFEST_SCHEMA_VERSION",
    "BlocksDocument",
    "ManifestPointer",
    "build_blocks_document",
    "build_manifest_pointer",
    "compute_content_hash",
    "delete_parsed_artifacts",
    "document_image_relative_key",
    "extract_text_from_blocks",
    "get_storage_uri",
    "image_media_type",
    "is_manifest_pointer",
    "persist_parse_images",
    "read_blocks_json",
    "summarize_blocks",
    "text_to_blocks",
    "try_read_existing_blocks",
    "write_blocks_json",
]
