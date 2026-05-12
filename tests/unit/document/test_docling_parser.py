"""Tests for Docling parser adapter."""

from datetime import UTC, datetime

import pytest

from apps.config import EnvConfig
from apps.shared.document.domain import DocumentDomain
from apps.shared.document.parsers.docling import (
    DoclingDocumentParser,
    _extract_markdown,
    _extract_task_id,
    _normalize_task_status,
    _ocr_enabled_for,
)


class _FakeStorage:
    def __init__(self, content: bytes = b"pdf"):
        self.content = content

    async def read(self, file_url: str) -> bytes:
        return self.content


@pytest.mark.asyncio
async def test_docling_submit_poll_and_fetch(monkeypatch):
    parser = DoclingDocumentParser(_FakeStorage())
    parser._base_url = "http://docling.test"

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

        async def post(self, url, headers=None, files=None, data=None):
            return _Response({"task_id": "docling-task-1"})

        async def get(self, url, headers=None):
            if "/result/" in url:
                return _Response({"documents": [{"md_content": "# Title\n\nBody text"}]})
            return _Response({"task_status": "success"})

    monkeypatch.setattr("apps.shared.document.parsers.docling.httpx.AsyncClient", _Client)

    doc = DocumentDomain(
        id=3,
        tenant_id=1,
        collection_id=1,
        filename="report.docx",
        file_url="report.docx",
        file_size=10,
        file_hash="hash",
        status="processing",
        owner_id=1,
        upload_date=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    submission = await parser.submit(doc)
    assert submission.job_id == "docling-task-1"
    assert await parser.poll(submission.job_id) == "completed"
    blocks_doc = await parser.fetch_result(doc, submission.job_id)
    assert blocks_doc["parser"] == "docling"
    assert len(blocks_doc["blocks"]) >= 1


@pytest.mark.asyncio
async def test_docling_requires_service_url(monkeypatch):
    monkeypatch.setattr(EnvConfig, "DOCLING_SERVICE_URL", "")
    monkeypatch.delenv("DOCLING_SERVICE_URL", raising=False)
    parser = DoclingDocumentParser(_FakeStorage())
    doc = DocumentDomain(
        id=1,
        tenant_id=1,
        collection_id=1,
        filename="a.pdf",
        file_url="a.pdf",
        file_size=1,
        file_hash="h",
        status="processing",
        owner_id=1,
        upload_date=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    with pytest.raises(ValueError, match="DOCLING_SERVICE_URL"):
        await parser.submit(doc)


@pytest.mark.asyncio
async def test_docling_poll_maps_failure_status(monkeypatch):
    parser = DoclingDocumentParser(_FakeStorage())
    parser._base_url = "http://docling.test"

    class _Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"task_status": "failure"}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            return _Response()

    monkeypatch.setattr("apps.shared.document.parsers.docling.httpx.AsyncClient", _Client)
    assert await parser.poll("job-1") == "failed"


@pytest.mark.asyncio
async def test_docling_poll_raises_when_task_not_found(monkeypatch):
    parser = DoclingDocumentParser(_FakeStorage())
    parser._base_url = "http://docling.test"

    class _Response:
        status_code = 404

        def raise_for_status(self):
            raise AssertionError("404 should be handled before raise_for_status")

        def json(self):
            return {"detail": "Task not found."}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            return _Response()

    monkeypatch.setattr("apps.shared.document.parsers.docling.httpx.AsyncClient", _Client)
    with pytest.raises(RuntimeError, match="Docling task not found"):
        await parser.poll("missing-job")


@pytest.mark.asyncio
async def test_docling_submit_uses_v1_async_endpoint_and_api_key(monkeypatch):
    parser = DoclingDocumentParser(_FakeStorage())
    parser._base_url = "http://docling.test"
    monkeypatch.setattr(EnvConfig, "DOCLING_API_KEY", "secret-key")
    captured: dict = {}

    class _Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"task_id": "task-99"}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, files=None, data=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["files"] = files
            return _Response()

    monkeypatch.setattr("apps.shared.document.parsers.docling.httpx.AsyncClient", _Client)

    doc = DocumentDomain(
        id=1,
        tenant_id=1,
        collection_id=1,
        filename="a.pdf",
        file_url="a.pdf",
        file_size=1,
        file_hash="h",
        status="processing",
        owner_id=1,
        upload_date=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    submission = await parser.submit(doc)
    assert submission.job_id == "task-99"
    assert captured["url"] == "http://docling.test/v1/convert/file/async"
    assert captured["headers"]["X-Api-Key"] == "secret-key"
    assert captured["files"] == [
        ("files", ("a.pdf", b"pdf")),
        ("to_formats", (None, "md")),
        ("to_formats", (None, "json")),
        ("do_ocr", (None, "false")),
        ("include_images", (None, "true")),
        ("abort_on_error", (None, "false")),
    ]


def test_ocr_enabled_for_images_only_by_default(monkeypatch):
    monkeypatch.setattr(EnvConfig, "DOCLING_DO_OCR", False)
    assert _ocr_enabled_for("spec.pdf") is False
    assert _ocr_enabled_for("scan.PNG") is True


def test_ocr_enabled_when_configured(monkeypatch):
    monkeypatch.setattr(EnvConfig, "DOCLING_DO_OCR", True)
    assert _ocr_enabled_for("spec.pdf") is True


@pytest.mark.asyncio
async def test_docling_fetch_result_uses_result_endpoint(monkeypatch):
    parser = DoclingDocumentParser(_FakeStorage())
    parser._base_url = "http://docling.test"
    captured: dict = {}

    class _Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"document": {"md_content": "# Nested\n\nBody"}}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            captured["url"] = url
            return _Response()

    monkeypatch.setattr("apps.shared.document.parsers.docling.httpx.AsyncClient", _Client)

    doc = DocumentDomain(
        id=1,
        tenant_id=1,
        collection_id=1,
        filename="a.pdf",
        file_url="a.pdf",
        file_size=1,
        file_hash="h",
        status="processing",
        owner_id=1,
        upload_date=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    blocks_doc = await parser.fetch_result(doc, "job-77")
    assert captured["url"] == "http://docling.test/v1/result/job-77"
    assert blocks_doc["parser"] == "docling"
    assert any(block.get("type") == "heading" for block in blocks_doc["blocks"])


@pytest.mark.asyncio
async def test_docling_fetch_result_falls_back_to_filename_when_empty(monkeypatch):
    parser = DoclingDocumentParser(_FakeStorage())
    parser._base_url = "http://docling.test"

    class _Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"documents": []}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            return _Response()

    monkeypatch.setattr("apps.shared.document.parsers.docling.httpx.AsyncClient", _Client)

    doc = DocumentDomain(
        id=1,
        tenant_id=1,
        collection_id=1,
        filename="fallback-name.pdf",
        file_url="a.pdf",
        file_size=1,
        file_hash="h",
        status="processing",
        owner_id=1,
        upload_date=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    blocks_doc = await parser.fetch_result(doc, "job-1")
    assert blocks_doc["blocks"][0]["text"] == "fallback-name.pdf"


def test_extract_markdown_reads_nested_document_field():
    markdown = _extract_markdown({"document": {"md_content": "Section one"}})
    assert markdown == "Section one"


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"task_id": "task-a"}, "task-a"),
        ({"id": "task-b"}, "task-b"),
        ({"job_id": "task-c"}, "task-c"),
        ({"task_id": ""}, None),
        ({}, None),
    ],
)
def test_extract_task_id(payload, expected):
    assert _extract_task_id(payload) == expected


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"task_status": "success"}, "success"),
        ({"status": "processing"}, "processing"),
        ({"task": {"state": "failed"}}, "failed"),
        ({}, "pending"),
    ],
)
def test_normalize_task_status(payload, expected):
    assert _normalize_task_status(payload) == expected


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"markdown": "Direct markdown"}, "Direct markdown"),
        ({"md": "Md field"}, "Md field"),
        ({"result": {"text": "Nested text"}}, "Nested text"),
        ({"documents": [{"md_content": "Doc one"}, {"md_content": "Doc two"}]}, "Doc one\n\nDoc two"),
        ([{"content": "List item"}], "List item"),
        ("not-a-dict", ""),
        ({}, ""),
    ],
)
def test_extract_markdown_payload_shapes(payload, expected):
    assert _extract_markdown(payload) == expected


@pytest.mark.asyncio
async def test_docling_parse_completes_on_success(monkeypatch):
    parser = DoclingDocumentParser(_FakeStorage())
    parser._base_url = "http://docling.test"

    class _Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"task_id": "job-parse"}

    class _PollResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"task_status": "completed"}

    class _ResultResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"markdown": "# Title\n\nBody"}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, files=None, data=None):
            return _Response()

        async def get(self, url, headers=None):
            if "/result/" in url:
                return _ResultResponse()
            return _PollResponse()

    monkeypatch.setattr("apps.shared.document.parsers.docling.httpx.AsyncClient", _Client)
    doc = DocumentDomain(
        id=1,
        tenant_id=1,
        collection_id=1,
        filename="a.pdf",
        file_url="a.pdf",
        file_size=1,
        file_hash="h",
        status="processing",
        owner_id=1,
        upload_date=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    blocks_doc = await parser.parse(doc)
    assert blocks_doc["parser"] == "docling"
    assert len(blocks_doc["blocks"]) >= 1


@pytest.mark.asyncio
async def test_docling_parse_raises_on_failed_poll(monkeypatch):
    parser = DoclingDocumentParser(_FakeStorage())
    parser._base_url = "http://docling.test"

    class _Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"task_id": "job-fail"}

    class _PollResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"task_status": "failed"}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, files=None, data=None):
            return _Response()

        async def get(self, url, headers=None):
            return _PollResponse()

    monkeypatch.setattr("apps.shared.document.parsers.docling.httpx.AsyncClient", _Client)
    doc = DocumentDomain(
        id=1,
        tenant_id=1,
        collection_id=1,
        filename="a.pdf",
        file_url="a.pdf",
        file_size=1,
        file_hash="h",
        status="processing",
        owner_id=1,
        upload_date=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    with pytest.raises(RuntimeError, match="Docling parse failed with status=failed"):
        await parser.parse(doc)


@pytest.mark.asyncio
async def test_docling_fetch_result_raises_when_status_202(monkeypatch):
    parser = DoclingDocumentParser(_FakeStorage())
    parser._base_url = "http://docling.test"

    class _Response:
        status_code = 202

        def raise_for_status(self):
            return None

        def json(self):
            return {}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            return _Response()

    monkeypatch.setattr("apps.shared.document.parsers.docling.httpx.AsyncClient", _Client)
    doc = DocumentDomain(
        id=1,
        tenant_id=1,
        collection_id=1,
        filename="a.pdf",
        file_url="a.pdf",
        file_size=1,
        file_hash="h",
        status="processing",
        owner_id=1,
        upload_date=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    with pytest.raises(RuntimeError, match="Docling result not ready"):
        await parser.fetch_result(doc, "job-202")


@pytest.mark.asyncio
async def test_docling_submit_raises_when_task_id_missing(monkeypatch):
    parser = DoclingDocumentParser(_FakeStorage())
    parser._base_url = "http://docling.test"

    class _Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"unexpected": "payload"}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, files=None, data=None):
            return _Response()

    monkeypatch.setattr("apps.shared.document.parsers.docling.httpx.AsyncClient", _Client)
    doc = DocumentDomain(
        id=1,
        tenant_id=1,
        collection_id=1,
        filename="a.pdf",
        file_url="a.pdf",
        file_size=1,
        file_hash="h",
        status="processing",
        owner_id=1,
        upload_date=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    with pytest.raises(RuntimeError, match="missing task_id"):
        await parser.submit(doc)


@pytest.mark.asyncio
async def test_docling_poll_maps_pending_status(monkeypatch):
    parser = DoclingDocumentParser(_FakeStorage())
    parser._base_url = "http://docling.test"

    class _Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"task_status": "processing"}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            return _Response()

    monkeypatch.setattr("apps.shared.document.parsers.docling.httpx.AsyncClient", _Client)
    assert await parser.poll("job-pending") == "pending"


@pytest.mark.asyncio
async def test_docling_headers_omit_api_key_when_unset(monkeypatch):
    parser = DoclingDocumentParser(_FakeStorage())
    parser._base_url = "http://docling.test"
    monkeypatch.setattr(EnvConfig, "DOCLING_API_KEY", "")
    captured: dict = {}

    class _Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"task_id": "task-no-key"}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, files=None, data=None):
            captured["headers"] = headers
            return _Response()

    monkeypatch.setattr("apps.shared.document.parsers.docling.httpx.AsyncClient", _Client)
    doc = DocumentDomain(
        id=1,
        tenant_id=1,
        collection_id=1,
        filename="a.pdf",
        file_url="a.pdf",
        file_size=1,
        file_hash="h",
        status="processing",
        owner_id=1,
        upload_date=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    await parser.submit(doc)
    assert "X-Api-Key" not in captured["headers"]


@pytest.mark.asyncio
async def test_docling_fetch_result_uses_json_blocks_when_available(monkeypatch):
    parser = DoclingDocumentParser(_FakeStorage())
    parser._base_url = "http://docling.test"

    class _Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "documents": [
                    {
                        "md_content": "# Ignored\n\nFallback body",
                        "json_content": {
                            "texts": [
                                {"text": "JSON heading", "label": "section_header"},
                                {"text": "JSON body", "label": "paragraph"},
                            ]
                        },
                    }
                ]
            }

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            return _Response()

    monkeypatch.setattr("apps.shared.document.parsers.docling.httpx.AsyncClient", _Client)

    doc = DocumentDomain(
        id=1,
        tenant_id=1,
        collection_id=1,
        filename="deck.pptx",
        file_url="deck.pptx",
        file_size=1,
        file_hash="h",
        status="processing",
        owner_id=1,
        upload_date=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    blocks_doc = await parser.fetch_result(doc, "job-json")
    assert blocks_doc["parser"] == "docling"
    assert blocks_doc["blocks"][0]["type"] == "heading"
    assert blocks_doc["blocks"][0]["text"] == "JSON heading"
    assert blocks_doc["blocks"][1]["text"] == "JSON body"
