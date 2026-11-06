"""Slack Stop button blocks."""

from apps.tenant_app_service.agent_ingress.slack.run_control_blocks import (
    ACTION_AGENT_RUN_STOP,
    build_run_status_blocks,
    build_thinking_placeholder_blocks,
)


def test_thinking_placeholder_includes_stop_action():
    blocks = build_thinking_placeholder_blocks(thinking_text="🤔 …", run_id="run-1")
    actions = next(b for b in blocks if b["type"] == "actions")
    btn = actions["elements"][0]
    assert btn["action_id"] == ACTION_AGENT_RUN_STOP
    assert btn["value"] == "run-1"


def test_run_status_blocks_have_no_actions():
    blocks = build_run_status_blocks(text="Request canceled.")
    assert len(blocks) == 1
    assert blocks[0]["type"] == "section"
