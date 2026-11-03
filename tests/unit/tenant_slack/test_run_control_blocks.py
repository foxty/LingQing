"""Slack Stop button blocks."""

from apps.tenant_app_service.agent_ingress.slack.run_control_blocks import (
    ACTION_AGENT_RUN_STOP,
    build_thinking_placeholder_blocks,
)


def test_thinking_placeholder_includes_stop_action():
    blocks = build_thinking_placeholder_blocks(thinking_text="🤔 …", run_id="run-1")
    actions = next(b for b in blocks if b["type"] == "actions")
    btn = actions["elements"][0]
    assert btn["action_id"] == ACTION_AGENT_RUN_STOP
    assert btn["value"] == "run-1"
