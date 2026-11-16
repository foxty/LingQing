import pytest

from apps.tenant_app_service.audit.service import UTF8_BOM


def test_audit_export_bom_prefix():
    assert UTF8_BOM == "\ufeff"