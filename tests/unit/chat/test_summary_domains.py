"""Unit tests for ThreadSummaryDomain token metrics."""

from apps.tenant_app_service.chat.domain import ThreadSummaryDomain


def _thread_summary(*, before: int, after: int) -> ThreadSummaryDomain:
    return ThreadSummaryDomain(
        thread_id="t1",
        tenant_id=1,
        version=1,
        summary_content="Summary",
        session_range={"from_session_id": "s1", "to_session_id": "s1", "session_count": 1},
        message_range={"from_time": None, "to_time": None, "count": 1},
        session_count=1,
        token_count_before=before,
        token_count_after=after,
    )


class TestThreadSummaryDomainMetrics:
    def test_get_token_savings(self):
        assert _thread_summary(before=1000, after=200).get_token_savings() == 800

    def test_get_compression_ratio(self):
        assert _thread_summary(before=1000, after=400).get_compression_ratio() == 0.4

    def test_get_compression_ratio_zero_before(self):
        assert _thread_summary(before=0, after=100).get_compression_ratio() == 0.0

    def test_format_token_metrics_compression(self):
        assert _thread_summary(before=1000, after=400).format_token_metrics() == "saved 600 tokens (40.0% of input)"

    def test_format_token_metrics_expansion(self):
        summary = _thread_summary(before=513, after=1313)
        assert summary.format_token_metrics() == "expanded by 800 tokens (255.9% of input)"
