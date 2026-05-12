"""Tests for MinerU parser adapter."""

from datetime import UTC, datetime

import pytest

from apps.shared.document.domain import DocumentDomain
from apps.shared.document.parsers.mineru import MinerUDocumentParser


class _FakeStorage:
    def __init__(self, content: bytes = b"pdf"):
        self.content = content

    async def read(self, file_url: str) -> bytes:
        return self.content


@pytest.mark.asyncio
async def test_mineru_submit_and_poll(monkeypatch):
    parser = MinerUDocumentParser(_FakeStorage())
    parser._base_url = "http://mineru.test"

    class _Response:
        def __init__(self, payload, status_code=200):
            self._payload = payload
            self.status_code = status_code
            self.content = b""
            self.headers = {"content-type": "application/json"}

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, files=None, data=None):
            return _Response({"task_id": "task-123"})

        async def get(self, url):
            if url.endswith("/result"):
                return _Response({"markdown": "# Title\n\nBody text"})
            return _Response({"status": "completed"})

    monkeypatch.setattr("apps.shared.document.parsers.mineru.httpx.AsyncClient", _Client)

    doc = DocumentDomain(
        id=2,
        tenant_id=1,
        collection_id=1,
        filename="paper.pdf",
        file_url="/tmp/paper.pdf",
        file_size=10,
        file_hash="hash",
        status="processing",
        owner_id=1,
        upload_date=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    submission = await parser.submit(doc)
    assert submission.job_id == "task-123"
    assert await parser.poll(submission.job_id) == "completed"
    blocks_doc = await parser.fetch_result(doc, submission.job_id)
    assert blocks_doc["parser"] == "mineru"
    assert len(blocks_doc["blocks"]) >= 1
