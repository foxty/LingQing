"""Unit tests for ThreadSummaryTrigger."""

from dataclasses import dataclass

import pytest

from apps.tenant_app_service.chat.thread_summary_manager import ThreadSummaryTrigger


@dataclass
class _FakeSessionSummary:
    summary_text: str


@pytest.fixture
def trigger() -> ThreadSummaryTrigger:
    return ThreadSummaryTrigger()


class TestThreadSummaryTrigger:
    @pytest.mark.asyncio
    async def test_standard_window_triggers_when_tokens_sufficient(self, trigger: ThreadSummaryTrigger):
        sessions = [_FakeSessionSummary(summary_text="x " * 3000) for _ in range(5)]

        result = await trigger.check("thread-1", sessions)

        assert result.should_trigger is True
        assert result.reason == "standard_window"
        assert result.session_count == 5
        assert result.estimated_tokens >= trigger.LATE_TRIGGER_MIN_TOKENS

    @pytest.mark.asyncio
    async def test_standard_window_delays_when_tokens_light(self, trigger: ThreadSummaryTrigger):
        sessions = [_FakeSessionSummary(summary_text="short summary") for _ in range(5)]

        result = await trigger.check("thread-1", sessions)

        assert result.should_trigger is False
        assert result.reason == "delaying_light_sessions_at_window"
        assert result.session_count == 5
        assert result.estimated_tokens < trigger.LATE_TRIGGER_MIN_TOKENS

    @pytest.mark.asyncio
    async def test_late_trigger_max_sessions_forces_summary(self, trigger: ThreadSummaryTrigger):
        sessions = [_FakeSessionSummary(summary_text="short summary") for _ in range(7)]

        result = await trigger.check("thread-1", sessions)

        assert result.should_trigger is True
        assert result.reason == "late_trigger_max_sessions"
        assert result.session_count == 7

    @pytest.mark.asyncio
    async def test_waiting_when_below_standard_window(self, trigger: ThreadSummaryTrigger):
        sessions = [_FakeSessionSummary(summary_text="short summary") for _ in range(3)]

        result = await trigger.check("thread-1", sessions)

        assert result.should_trigger is False
        assert result.reason == "waiting"
        assert result.session_count == 3
