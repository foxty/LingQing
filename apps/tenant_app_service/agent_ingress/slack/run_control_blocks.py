"""Block Kit controls for in-flight Slack agent runs."""

from __future__ import annotations

ACTION_AGENT_RUN_STOP = "agent_run_stop"


def build_thinking_placeholder_blocks(*, thinking_text: str, run_id: str) -> list[dict]:
    """Thinking line plus Stop (uses ``run_id`` as button value; thread resolved server-side)."""
    return [
        *build_run_status_blocks(text=thinking_text),
        {
            "type": "actions",
            "block_id": f"run_control_{run_id}",
            "elements": [
                {
                    "type": "button",
                    "action_id": ACTION_AGENT_RUN_STOP,
                    "text": {"type": "plain_text", "text": "Stop", "emoji": True},
                    "style": "danger",
                    "value": run_id,
                }
            ],
        },
    ]


def build_run_status_blocks(*, text: str) -> list[dict]:
    """Single status line without run controls (canceled, already finished, etc.)."""
    return [{"type": "section", "text": {"type": "mrkdwn", "text": text}}]
