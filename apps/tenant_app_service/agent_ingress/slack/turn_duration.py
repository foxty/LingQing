"""Footer copy for how long one Slack chat turn took.

``PreparedChatStream.run_created_at`` is set when the agent run row is
created during prepare. Slack ingress forwards it as ``turn_started_at``;
``apply_turn_footer_to_outbound`` appends the footer (and feedback actions)
on the final outbound payload. Cancel uses the same ``run.created_at``
baseline via ``load_slack_turn_started_at``.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agent_ingress.slack.feedback_blocks import append_feedback_actions

logger = get_logger(__name__)

TURN_DURATION_BLOCK_ID = "turn_duration"
SLACK_MAX_BLOCKS = 50

_ONE_TENTH = Decimal("0.1")
_SIXTY = Decimal(60)
_MINUTE_TENTHS = 600


def format_slack_turn_footer(elapsed_seconds: float | None) -> str | None:
    """Format one turn's elapsed seconds, or return None when it must be hidden.

    Rounding is half-up to 1 decimal place. Values that round to under 0.1s
    use ``Took <0.1s``. Values that round to 60.0s or more use minutes, and a
    remainder that rounds to 60.0s carries into the next minute.
    """
    duration = _non_negative_duration(elapsed_seconds)
    if duration is None:
        return None

    minutes = int(duration // _SIXTY)
    remainder = duration - (Decimal(minutes) * _SIXTY)
    remainder_tenths = _half_up_tenths(remainder)
    if remainder_tenths >= _MINUTE_TENTHS:
        minutes += 1
        remainder_tenths = 0
    if minutes <= 0:
        if remainder_tenths < 1:
            return "Took <0.1s"
        return f"Took {_seconds_label(remainder_tenths)}s"
    return f"Took {minutes}m {_seconds_label(remainder_tenths)}s"


def elapsed_seconds_since(started_at: datetime | None, *, now: datetime | None = None) -> float | None:
    """Seconds from ``started_at`` until ``now`` (default: current UTC time)."""
    if started_at is None:
        return None
    start = _as_utc(started_at)
    current = _as_utc(now or datetime.now(UTC))
    return (current - start).total_seconds()


def turn_duration_context_block(footer: str) -> dict[str, Any]:
    """One Slack context line. ``plain_text`` keeps ``<`` literal on every client."""
    return {
        "type": "context",
        "block_id": TURN_DURATION_BLOCK_ID,
        "elements": [{"type": "plain_text", "text": footer, "emoji": False}],
    }


def append_duration_footer_line(text: str, footer: str) -> str:
    """Put the footer on its own line under the notification fallback text."""
    if not footer:
        return text
    if not text:
        return footer
    if text == footer or text.endswith(f"\n{footer}"):
        return text
    return f"{text}\n{footer}"


def apply_turn_footer_to_outbound(
    *,
    text: str,
    blocks: list[dict[str, Any]],
    turn_started_at: datetime | None = None,
    now: datetime | None = None,
    message_id: str | None = None,
    footer_text: str | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Append feedback actions and/or duration footer to one outbound Slack payload."""
    footer = footer_text
    if footer is None and turn_started_at is not None:
        footer = format_slack_turn_footer(elapsed_seconds_since(turn_started_at, now=now))

    original_blocks = list(blocks)
    result_blocks = list(blocks)
    if message_id:
        result_blocks = append_feedback_actions(original_blocks, message_id)
    if footer and original_blocks:
        result_blocks = [*result_blocks, turn_duration_context_block(footer)]
    if footer:
        text = append_duration_footer_line(text, footer)
    return text, result_blocks


async def load_slack_turn_started_at(
    db: AsyncSession,
    tenant_id: int,
    run_id: str | None,
) -> datetime | None:
    """Read the run's creation time. Missing or unreadable runs hide the footer."""
    if not run_id:
        return None
    try:
        from apps.tenant_app_service.chat.infrastructure.persistence.agent_run_repository import (
            AgentRunRepository,
        )

        run = await AgentRunRepository(db).get_run(tenant_id, run_id)
    except Exception:
        logger.warning("Slack turn duration skipped: could not read run %s", run_id)
        return None
    if run is None:
        return None
    return run.created_at


def _non_negative_duration(elapsed_seconds: float | None) -> Decimal | None:
    if elapsed_seconds is None or isinstance(elapsed_seconds, bool):
        return None
    try:
        value = float(elapsed_seconds)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or value < 0:
        return None
    return Decimal(str(value))


def _half_up_tenths(duration: Decimal) -> int:
    quantized = duration.quantize(_ONE_TENTH, rounding=ROUND_HALF_UP)
    return int(quantized * 10)


def _seconds_label(tenths: int) -> str:
    return f"{tenths / 10:.1f}"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
