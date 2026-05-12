"""Extract and sanitize text from various document formats.

Used in Flow 1 (upload) to extract raw text content from documents.
"""

import os
import tempfile
from typing import TYPE_CHECKING

from apps.shared.infra.storage.paths import resolve_storage_ref

if TYPE_CHECKING:
    from apps.shared.infra.storage import FileStorage

from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


class DocumentTextExtractor:
    """Extract and sanitize text from various document formats.

    Supports PDF, DOCX, PPT, HTML, Markdown, and Excel files.
    Uses langchain document loaders for extraction.
    """

    def __init__(self, file_storage: "FileStorage"):
        self.file_storage = file_storage

    async def extract_text(self, file_url: str, filename: str, *, tenant_id: int) -> str | None:
        """Extract text content from a document file.

        Downloads the file temporarily, extracts text, and sanitizes.

        Args:
            file_url: Storage URL or path
            filename: Original filename (used for extension detection)

        Returns:
            Extracted and sanitized text, or None if extraction fails or content is empty.
        """
        ext = os.path.splitext(filename)[1].lower()
        if ext not in self._supported_extensions():
            logger.warning("Unsupported file extension: %s", ext)
            return None

        local_path = None
        try:
            local_path = await self._get_local_path(resolve_storage_ref(tenant_id, file_url))
            text = await self._extract_from_file(local_path, ext)
            sanitized = self.sanitize_text(text)
            # Return None if sanitized result is empty (no meaningful content)
            return sanitized if sanitized else None
        except Exception as e:
            logger.warning("Failed to extract text from %s: %s", filename, e)
            return None
        finally:
            if local_path and os.path.exists(local_path):
                try:
                    os.remove(local_path)
                except Exception:
                    pass

    @staticmethod
    def _supported_extensions() -> set[str]:
        from apps.config import AppConfig

        return AppConfig.SUPPORTED_DOCUMENT_EXTENSIONS

    async def _get_local_path(self, file_url: str) -> str:
        """Get local path for file, downloading if necessary."""
        # Check if file_storage has get_local_path method (new interface)
        if hasattr(self.file_storage, "get_local_path"):
            return await self.file_storage.get_local_path(file_url)

        # Fallback: download to temp file using get() method
        content = await self.file_storage.get(file_url)
        suffix = os.path.splitext(file_url)[1] or ".tmp"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            return tmp.name

    async def _extract_from_file(self, local_path: str, ext: str) -> str:
        """Extract text using langchain document loaders."""
        from langchain_community.document_loaders import (
            Docx2txtLoader,
            PyPDFLoader,
            UnstructuredHTMLLoader,
            UnstructuredMarkdownLoader,
            UnstructuredPowerPointLoader,
            UnstructuredWordDocumentLoader,
        )

        if ext == ".pdf":
            loader = PyPDFLoader(local_path)
        elif ext == ".docx":
            try:
                loader = Docx2txtLoader(local_path)
            except Exception:
                loader = UnstructuredWordDocumentLoader(local_path)
        elif ext in [".ppt", ".pptx"]:
            loader = UnstructuredPowerPointLoader(local_path)
        elif ext in [".html", ".htm"]:
            loader = UnstructuredHTMLLoader(local_path)
        elif ext == ".md":
            loader = UnstructuredMarkdownLoader(local_path)
        elif ext in {".xlsx", ".xls"}:
            return _extract_excel(local_path, ext)
        else:
            raise ValueError(f"Unsupported extension: {ext}")

        docs = loader.load()
        return "\n\n".join(doc.page_content for doc in docs if doc.page_content)

    @staticmethod
    def sanitize_text(text: str | None) -> str | None:
        """Sanitize extracted text.

        - Fixes surrogate pairs and encoding issues using ftfy
        - Removes excessive whitespace
        - Removes control characters
        - Truncates to reasonable length

        Args:
            text: Text to sanitize (can be None)

        Returns:
            Sanitized text or None if input is None
        """
        if text is None:
            return None

        # Return empty string as-is
        if text == "":
            return ""

        try:
            import ftfy

            # Fix encoding issues and surrogate pairs
            text = ftfy.fix_text(text)
        except ImportError:
            # ftfy not installed, skip encoding fixes
            pass

        import re

        # Remove control characters except newlines and tabs
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", text)

        # Normalize whitespace (collapse multiple spaces, but preserve tabs)
        text = re.sub(r" +", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)

        # Truncate to 1MB of text (reasonable limit for FTS)
        max_chars = 1_000_000
        if len(text) > max_chars:
            text = text[:max_chars]
            logger.info("Truncated extracted text to %d characters", max_chars)

        result = text.strip()
        return result if result else None


def _extract_excel(local_path: str, ext: str) -> str:
    """Extract searchable text from Excel workbooks, one sheet at a time."""
    import pandas as pd

    engine = "xlrd" if ext == ".xls" else "openpyxl"
    sheets = pd.read_excel(local_path, sheet_name=None, dtype=object, engine=engine)
    parts: list[str] = []
    for sheet_name, frame in sheets.items():
        if frame is None or frame.empty:
            continue
        cleaned = frame.where(frame.notna(), "")
        parts.append(str(sheet_name))
        csv_text = cleaned.to_csv(index=False).strip()
        if csv_text:
            parts.append(csv_text)
    return "\n\n".join(parts)
