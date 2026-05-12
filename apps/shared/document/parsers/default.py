"""Built-in synchronous document parser using LangChain extractors."""

from __future__ import annotations

from apps.shared.document.domain import DocumentDomain
from apps.shared.document.manifest import build_blocks_document, text_to_blocks
from apps.shared.document.parsers.base import ParseSubmission
from apps.shared.document.text_extractor import DocumentTextExtractor
from apps.shared.infra.storage import FileStorage


class DefaultDocumentParser:
    """Wrap DocumentTextExtractor and emit canonical blocks IR."""

    name = "default"

    def __init__(self, file_storage: FileStorage):
        self._extractor = DocumentTextExtractor(file_storage)

    @property
    def is_async(self) -> bool:
        return False

    async def parse(self, document: DocumentDomain) -> dict:
        extracted = await self._extractor.extract_text(
            document.file_url,
            document.filename,
            tenant_id=document.tenant_id,
        )
        text = extracted if extracted else document.filename
        blocks = text_to_blocks(text)
        return build_blocks_document(parser=self.name, blocks=blocks)

    async def submit(self, document: DocumentDomain) -> ParseSubmission:
        raise NotImplementedError("Default parser does not support async submission")

    async def poll(self, job_id: str) -> str:
        raise NotImplementedError("Default parser does not support async polling")

    async def fetch_result(self, document: DocumentDomain, job_id: str) -> dict:
        raise NotImplementedError("Default parser does not support async fetch")
