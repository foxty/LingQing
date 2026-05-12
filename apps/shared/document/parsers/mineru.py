"""MinerU external service parser adapter."""

from __future__ import annotations

import io
import zipfile
from typing import Any

import httpx

from apps.config import EnvConfig
from apps.shared.document.domain import DocumentDomain
from apps.shared.document.manifest import build_blocks_document
from apps.shared.document.parsers.base import ParseSubmission
from apps.shared.document.parsers.markdown_blocks import markdown_to_blocks
from apps.shared.document.types import ParseJobStatus
from apps.shared.infra.storage import FileStorage
from apps.shared.infra.storage.paths import resolve_storage_ref
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)

_TERMINAL_STATUSES = {"completed", "failed", "error", "cancelled"}
_PENDING_STATUSES = {"pending", "processing", "queued", "running"}


class MinerUDocumentParser:
    """Async adapter for MinerU FastAPI service."""

    name = "mineru"

    def __init__(self, file_storage: FileStorage):
        self._file_storage = file_storage
        self._base_url = (EnvConfig.MINERU_SERVICE_URL or "").rstrip("/")

    @property
    def is_async(self) -> bool:
        return True

    def _require_base_url(self) -> str:
        if not self._base_url:
            raise ValueError("MINERU_SERVICE_URL is not configured")
        return self._base_url

    async def parse(self, document: DocumentDomain) -> dict:
        submission = await self.submit(document)
        status = await self.poll(submission.job_id)
        if status != ParseJobStatus.COMPLETED:
            raise RuntimeError(f"MinerU parse failed with status={status}")
        return await self.fetch_result(document, submission.job_id)

    async def submit(self, document: DocumentDomain) -> ParseSubmission:
        base_url = self._require_base_url()
        resolved = resolve_storage_ref(document.tenant_id, document.file_url)
        file_bytes = await self._file_storage.read(resolved)
        async with httpx.AsyncClient(timeout=EnvConfig.MINERU_TASK_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{base_url}/tasks",
                files={"files": (document.filename, file_bytes)},
                data={"return_md": "true"},
            )
            response.raise_for_status()
            payload = response.json()

        task_id = _extract_task_id(payload)
        if not task_id:
            raise RuntimeError(f"MinerU submit response missing task_id: {payload}")
        return ParseSubmission(job_id=task_id)

    async def poll(self, job_id: str) -> str:
        base_url = self._require_base_url()
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{base_url}/tasks/{job_id}")
            response.raise_for_status()
            payload = response.json()
        status = _normalize_status(payload)
        if status in _TERMINAL_STATUSES:
            return ParseJobStatus.COMPLETED if status == ParseJobStatus.COMPLETED else ParseJobStatus.FAILED
        return ParseJobStatus.PENDING if status in _PENDING_STATUSES else status

    async def fetch_result(self, document: DocumentDomain, job_id: str) -> dict:
        base_url = self._require_base_url()
        async with httpx.AsyncClient(timeout=EnvConfig.MINERU_TASK_TIMEOUT_SECONDS) as client:
            response = await client.get(f"{base_url}/tasks/{job_id}/result")
            if response.status_code == 202:
                raise RuntimeError("MinerU result not ready")
            response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        if "application/zip" in content_type or response.content[:2] == b"PK":
            markdown = _extract_markdown_from_zip(response.content)
        else:
            payload = response.json()
            markdown = _extract_markdown_from_json(payload)

        if not markdown.strip():
            markdown = document.filename

        blocks = markdown_to_blocks(markdown)
        return build_blocks_document(parser=self.name, blocks=blocks)


def _extract_task_id(payload: dict[str, Any]) -> str | None:
    for key in ("task_id", "id", "job_id"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("task_id", "id", "job_id"):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def _normalize_status(payload: dict[str, Any]) -> str:
    for key in ("status", "state"):
        value = payload.get(key)
        if isinstance(value, str):
            return value.lower()
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("status", "state"):
            value = data.get(key)
            if isinstance(value, str):
                return value.lower()
    return "pending"


def _extract_markdown_from_json(payload: dict[str, Any]) -> str:
    for key in ("markdown", "md", "content", "text"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
    results = payload.get("results")
    if isinstance(results, dict):
        for value in results.values():
            if isinstance(value, dict):
                md = value.get("md_content") or value.get("markdown")
                if isinstance(md, str):
                    return md
    return ""


def _extract_markdown_from_zip(content: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        md_names = [name for name in archive.namelist() if name.lower().endswith(".md")]
        if not md_names:
            return ""
        md_names.sort()
        with archive.open(md_names[0]) as md_file:
            return md_file.read().decode("utf-8", errors="replace")

