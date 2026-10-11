"""Tests for Slack feedback Block Kit helpers."""

from apps.tenant_app_service.agent_ingress.slack.feedback_blocks import (
    ACTION_FEEDBACK_NEGATIVE,
    ACTION_FEEDBACK_POSITIVE,
    append_feedback_actions,
    build_feedback_ack_blocks,
    build_feedback_blocks,
    replace_feedback_actions,
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


def test_append_feedback_actions_keeps_content_blocks():
    content = [{"type": "table", "rows": []}, {"type": "image", "alt_text": "Plot"}]
    blocks = append_feedback_actions(content, "msg_test_004")
    assert blocks[0]["type"] == "table"
    assert blocks[1]["type"] == "image"
    assert blocks[2]["type"] == "actions"
    assert blocks[2]["block_id"] == "feedback_msg_test_004"


def test_replace_feedback_actions_preserves_table():
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": "Intro"}},
        {"type": "table", "rows": [[{"type": "raw_text", "text": "A"}]]},
        {"type": "actions", "block_id": "feedback_msg_test_005", "elements": []},
    ]
    updated = replace_feedback_actions(blocks, "msg_test_005", current_rating="positive")
    assert updated[1]["type"] == "table"
    assert updated[2]["type"] == "actions"
    assert updated[2]["elements"][0]["style"] == "primary"


def test_build_feedback_ack_blocks_replaces_actions():
    blocks = build_feedback_ack_blocks("Reply text", "positive")
    assert len(blocks) == 2
    assert blocks[1]["type"] == "context"
