"""Tests for storage path helpers."""

from pathlib import Path

import pytest

from apps.shared.infra.storage.paths import normalize_storage_key, resolve_storage_ref


@pytest.mark.asyncio
async def test_normalize_and_resolve_relative_key(monkeypatch, tmp_path):
    tenant_docs = tmp_path / "tenant_2" / "documents"
    tenant_docs.mkdir(parents=True)
    monkeypatch.setattr(
        "apps.shared.infra.storage.paths.get_tenant_documents_path",
        lambda tenant_id: str(tenant_docs),
    )

    absolute = str(tenant_docs / "report.pdf")
    assert normalize_storage_key(2, absolute) == "report.pdf"
    assert resolve_storage_ref(2, "report.pdf") == absolute


def test_cloud_ref_unchanged():
    ref = "s3://bucket/tenant/report.pdf"
    assert normalize_storage_key(2, ref) == ref
    assert resolve_storage_ref(2, ref) == ref
