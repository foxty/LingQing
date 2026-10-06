"""Block Kit helpers for Slack message feedback buttons."""

from __future__ import annotations

from typing import Literal

FeedbackRating = Literal["positive", "negative"] | None

ACTION_FEEDBACK_POSITIVE = "feedback_positive"
ACTION_FEEDBACK_NEGATIVE = "feedback_negative"
VIEW_FEEDBACK_COMMENT = "feedback_comment_modal"


def build_feedback_blocks(
    text: str,
    message_id: str,
    *,
    current_rating: FeedbackRating = None,
) -> list[dict]:
    """Build Slack blocks with AI reply text and thumbs up/down buttons."""
    positive_style = "primary" if current_rating == "positive" else None
    negative_style = "danger" if current_rating == "negative" else None
    positive_label = "👍 Helpful · selected" if current_rating == "positive" else "👍 Helpful"
    negative_label = "👎 Not helpful · selected" if current_rating == "negative" else "👎 Not helpful"

    positive_btn: dict = {
        "type": "button",
        "action_id": ACTION_FEEDBACK_POSITIVE,
        "text": {"type": "plain_text", "text": positive_label, "emoji": True},
        "value": message_id,
    }
    negative_btn: dict = {
        "type": "button",
        "action_id": ACTION_FEEDBACK_NEGATIVE,
        "text": {"type": "plain_text", "text": negative_label, "emoji": True},
        "value": message_id,
    }
    if positive_style:
        positive_btn["style"] = positive_style
    if negative_style:
        negative_btn["style"] = negative_style

    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": text}},
        {
            "type": "actions",
            "block_id": f"feedback_{message_id}",
            "elements": [positive_btn, negative_btn],
        },
    ]


def build_feedback_ack_blocks(text: str, rating: FeedbackRating) -> list[dict]:
    """Replace action buttons with a thank-you context block."""
    label = "👍 Thanks for the feedback!" if rating == "positive" else "👎 Thanks — we'll use this to improve."
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": text}},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": label}]},
    ]


def build_feedback_comment_modal(*, message_id: str, trigger_id: str) -> dict:
    """Build views.open payload for optional negative feedback comment."""
    return {
        "trigger_id": trigger_id,
        "view": {
            "type": "modal",
            "callback_id": VIEW_FEEDBACK_COMMENT,
            "private_metadata": message_id,
            "title": {"type": "plain_text", "text": "Feedback"},
            "submit": {"type": "plain_text", "text": "Submit"},
            "close": {"type": "plain_text", "text": "Skip"},
            "blocks": [
                {
                    "type": "input",
                    "block_id": "comment_block",
                    "optional": True,
                    "label": {"type": "plain_text", "text": "What was wrong or unhelpful?"},
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "comment_input",
                        "multiline": True,
                        "max_length": 2000,
                    },
                }
            ],
        },
    }
