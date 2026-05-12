"""Docling Serve external parser adapter."""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any

import httpx

from apps.config import EnvConfig
from apps.shared.document.domain import DocumentDomain
from apps.shared.document.manifest import build_blocks_document
from apps.shared.document.parsers.base import ParseSubmission
from apps.shared.document.parsers.docling_blocks import docling_json_to_blocks, supplement_tables_from_markdown
from apps.shared.document.parsers.markdown_blocks import markdown_to_blocks
from apps.shared.document.types import ParseJobStatus
from apps.shared.infra.storage import FileStorage
from apps.shared.infra.storage.paths import resolve_storage_ref
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)

_TERMINAL_SUCCESS = {"success", "completed"}
_TERMINAL_FAILURE = {"failure", "failed", "error", "cancelled"}
_PENDING_STATUSES = {"pending", "started", "processing", "queued", "running"}
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".gif"}


class DoclingDocumentParser:
    """Async adapter for docling-serve v1 HTTP API."""

    name = "docling"

    def __init__(self, file_storage: FileStorage):
        self._file_storage = file_storage
        self._base_url = (EnvConfig.DOCLING_SERVICE_URL or "").rstrip("/")

    @property
    def is_async(self) -> bool:
        return True

    def _require_base_url(self) -> str:
        base_url = (self._base_url or os.getenv("DOCLING_SERVICE_URL") or "").rstrip("/")
        if not base_url:
            raise ValueError("DOCLING_SERVICE_URL is not configured")
        return base_url

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"accept": "application/json"}
        api_key = (EnvConfig.DOCLING_API_KEY or "").strip()
        if api_key:
            headers["X-Api-Key"] = api_key
        return headers

    def _convert_multipart(self, *, filename: str, file_bytes: bytes) -> list[tuple[str, tuple]]:
        do_ocr = "true" if _ocr_enabled_for(filename) else "false"
        return [
            ("files", (filename, file_bytes)),
            ("to_formats", (None, "md")),
            ("to_formats", (None, "json")),
            ("do_ocr", (None, do_ocr)),
            ("include_images", (None, "true")),
            ("abort_on_error", (None, "false")),
        ]

    async def parse(self, document: DocumentDomain) -> dict:
        submission = await self.submit(document)
        deadline = time.monotonic() + EnvConfig.DOCLING_TASK_TIMEOUT_SECONDS
        poll_interval_seconds = 2
        while time.monotonic() < deadline:
            status = await self.poll(submission.job_id)
            if status == ParseJobStatus.COMPLETED:
                return await self.fetch_result(document, submission.job_id)
            if status == ParseJobStatus.FAILED:
                raise RuntimeError(f"Docling parse failed with status={status}")
            await asyncio.sleep(poll_interval_seconds)
        raise RuntimeError("Docling parse timed out")

    async def submit(self, document: DocumentDomain) -> ParseSubmission:
        base_url = self._require_base_url()
        resolved = resolve_storage_ref(document.tenant_id, document.file_url)
        file_bytes = await self._file_storage.read(resolved)
        async with httpx.AsyncClient(timeout=EnvConfig.DOCLING_TASK_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{base_url}/v1/convert/file/async",
                headers=self._headers(),
                files=self._convert_multipart(filename=document.filename, file_bytes=file_bytes),
            )
            response.raise_for_status()
            payload = response.json()

        task_id = _extract_task_id(payload)
        if not task_id:
            raise RuntimeError(f"Docling submit response missing task_id: {payload}")
        return ParseSubmission(job_id=task_id)

    async def poll(self, job_id: str) -> str:
        base_url = self._require_base_url()
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{base_url}/v1/status/poll/{job_id}",
                headers=self._headers(),
            )
            if response.status_code == 404:
                raise RuntimeError(
                    f"Docling task not found: {job_id}. "
                    "The parser may have restarted or the job expired; reparse the document."
                )
            response.raise_for_status()
            payload = response.json()
        status = _normalize_task_status(payload)
        if status in _TERMINAL_SUCCESS:
            return ParseJobStatus.COMPLETED
        if status in _TERMINAL_FAILURE:
            return ParseJobStatus.FAILED
        return ParseJobStatus.PENDING if status in _PENDING_STATUSES else status

    async def fetch_result(self, document: DocumentDomain, job_id: str) -> dict:
        base_url = self._require_base_url()
        async with httpx.AsyncClient(timeout=EnvConfig.DOCLING_TASK_TIMEOUT_SECONDS) as client:
            response = await client.get(
                f"{base_url}/v1/result/{job_id}",
                headers=self._headers(),
            )
            if response.status_code == 202:
                raise RuntimeError("Docling result not ready")
            response.raise_for_status()

        payload = response.json()
        blocks = _blocks_from_payload(payload)
        if not blocks:
            markdown = _extract_markdown(payload)
            if not markdown.strip():
                markdown = document.filename
            blocks = markdown_to_blocks(markdown)
        return build_blocks_document(parser=self.name, blocks=blocks)


def _ocr_enabled_for(filename: str) -> bool:
    if EnvConfig.DOCLING_DO_OCR:
        return True
    return Path(filename).suffix.lower() in _IMAGE_SUFFIXES


def _extract_task_id(payload: dict[str, Any]) -> str | None:
    for key in ("task_id", "id", "job_id"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _normalize_task_status(payload: dict[str, Any]) -> str:
    for key in ("task_status", "status", "state"):
        value = payload.get(key)
        if isinstance(value, str):
            return value.lower()
    task = payload.get("task")
    if isinstance(task, dict):
        for key in ("task_status", "status", "state"):
            value = task.get(key)
            if isinstance(value, str):
                return value.lower()
    return "pending"


def _blocks_from_payload(payload: dict[str, Any] | list[Any]) -> list[dict[str, Any]] | None:
    json_content = _extract_json_content(payload)
    if not json_content:
        return None
    blocks = docling_json_to_blocks(json_content)
    if not blocks:
        return None
    markdown = _extract_markdown(payload)
    if markdown.strip():
        blocks = supplement_tables_from_markdown(blocks, markdown)
    return blocks


def _extract_json_content(payload: dict[str, Any] | list[Any]) -> dict[str, Any] | None:
    if isinstance(payload, list):
        for item in payload:
            json_content = _extract_json_content(item)
            if json_content:
                return json_content
        return None

    if not isinstance(payload, dict):
        return None

    if isinstance(payload.get("texts"), list):
        return payload

    for key in ("json_content", "document", "result", "data"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            if isinstance(nested.get("texts"), list):
                return nested
            json_content = _extract_json_content(nested)
            if json_content:
                return json_content

    documents = payload.get("documents")
    if isinstance(documents, list):
        for doc in documents:
            if not isinstance(doc, dict):
                continue
            json_content = doc.get("json_content")
            if isinstance(json_content, dict) and isinstance(json_content.get("texts"), list):
                return json_content
            if isinstance(doc.get("texts"), list):
                return doc
    return None


def _extract_markdown(payload: dict[str, Any] | list[Any]) -> str:
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                markdown = _extract_markdown(item)
                if markdown.strip():
                    return markdown
        return ""

    if not isinstance(payload, dict):
        return ""

    for key in ("markdown", "md", "md_content", "content", "text"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value

    for key in ("document", "result", "data"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            markdown = _extract_markdown(nested)
            if markdown.strip():
                return markdown

    documents = payload.get("documents")
    if isinstance(documents, list):
        parts: list[str] = []
        for doc in documents:
            if not isinstance(doc, dict):
                continue
            markdown = _extract_markdown(doc)
            if markdown.strip():
                parts.append(markdown.strip())
        return "\n\n".join(parts)

    return ""
