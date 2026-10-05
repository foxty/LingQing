"""Tests for Slack feedback Block Kit helpers."""

from apps.tenant_app_service.agent_ingress.slack.feedback_blocks import (
    ACTION_FEEDBACK_NEGATIVE,
    ACTION_FEEDBACK_POSITIVE,
    build_feedback_ack_blocks,
    build_feedback_blocks,
)


def test_build_feedback_blocks_includes_actions():
    blocks = build_feedback_blocks("Hello world", "msg_test_001")
    assert len(blocks) == 2
    assert blocks[0]["type"] == "section"
    assert blocks[1]["type"] == "actions"
    elements = blocks[1]["elements"]
    assert elements[0]["action_id"] == ACTION_FEEDBACK_POSITIVE
    assert elements[1]["action_id"] == ACTION_FEEDBACK_NEGATIVE
    assert elements[0]["value"] == "msg_test_001"


def test_build_feedback_blocks_highlights_selected_rating():
    blocks = build_feedback_blocks("Reply", "msg_test_002", current_rating="negative")
    negative = blocks[1]["elements"][1]
    assert negative["style"] == "danger"
    assert "selected" in negative["text"]["text"].lower()


def test_build_feedback_blocks_marks_positive_selection():
    blocks = build_feedback_blocks("Reply", "msg_test_003", current_rating="positive")
    positive = blocks[1]["elements"][0]
    assert positive["style"] == "primary"
    assert "selected" in positive["text"]["text"].lower()


def test_build_feedback_ack_blocks_replaces_actions():
    blocks = build_feedback_ack_blocks("Reply text", "positive")
    assert len(blocks) == 2
    assert blocks[1]["type"] == "context"
