"""Document parser port and shared types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from apps.shared.document.domain import DocumentDomain
from apps.shared.document.types import ParseJobStatus


@dataclass(frozen=True)
class ParseSubmission:
    """Async parser submission result."""

    job_id: str


class DocumentParserPort(Protocol):
    """Adapter interface for document parsing engines."""

    name: str

    @property
    def is_async(self) -> bool:
        """Whether parsing completes via background polling."""
        ...

    async def parse(self, document: DocumentDomain) -> dict:
        """Run synchronous parse and return blocks.json document."""
        ...

    async def submit(self, document: DocumentDomain) -> ParseSubmission:
        """Submit async parse job."""
        ...

    async def poll(self, job_id: str) -> ParseJobStatus | str:
        """Poll async job. Returns a ParseJobStatus, or a vendor-specific status string."""
        ...

    async def fetch_result(self, document: DocumentDomain, job_id: str) -> dict:
        """Fetch blocks.json document from completed async job."""
        ...
