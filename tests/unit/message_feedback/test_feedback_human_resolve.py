"""Tests for feedback human message resolution."""

from apps.tenant_app_service.message_feedback.domain import FeedbackTargetMessage
from apps.tenant_app_service.message_feedback.service import _resolve_human_message


def test_resolve_human_message_prefers_trigger_over_session():
    ai = FeedbackTargetMessage(
        id=1,
        message_id="ai_1",
        thread_id="t1",
        session_id="s1",
        agent_id=1,
        content="answer",
        trigger_message_id="human_1",
    )
    result = _resolve_human_message(
        thread_id="t1",
        session_id="s1",
        ai_message=ai,
        human_by_trigger={("t1", "human_1"): "question"},
        human_by_session={("t1", "s1"): "wrong"},
    )
    assert result == "question"
