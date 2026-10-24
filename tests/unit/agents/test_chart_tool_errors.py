"""Chart tool error formatting."""

from apps.tenant_app_service.agents.tools.chart_support import exception_detail


def test_exception_detail_uses_string_when_present():
    assert exception_detail(RuntimeError("column missing")) == "column missing"


def test_exception_detail_falls_back_to_type_when_empty():
    class EmptyError(Exception):
        def __str__(self) -> str:
            return "   "

    assert exception_detail(EmptyError()) == "EmptyError"
